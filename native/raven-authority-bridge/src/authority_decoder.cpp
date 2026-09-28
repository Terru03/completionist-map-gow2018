#include "authority_decoder.h"
#include "chest_authority.h"

#include <zlib.h>

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <optional>
#include <set>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "raven_catalogue.generated.h"

namespace completionist {
namespace {

constexpr std::size_t kMaxCarrierBytes = 0x4800;
constexpr std::size_t kMaxTokenCount = 4096;
constexpr std::size_t kMaxParseSteps = 16384;
constexpr std::size_t kMaxParsePaths = 64;
constexpr std::size_t kMaxCandidates = 128;
constexpr std::size_t kMaxLengthPositions = 64;

struct Header {
  std::uint16_t section0_count;
  std::uint16_t blob_offset;
  std::uint16_t pair_count;
  std::uint16_t row_count;
  std::uint16_t record_count;
  std::uint16_t blob_length;
  std::uint16_t scalar_c;
  std::uint16_t compressed_length;
};

struct Token {
  std::uint8_t tag = 0;
  std::uint32_t payload = 0;
  std::uint8_t width = 0;
};

struct Row {
  std::uint16_t first_pair = 0;
  std::uint16_t pair_count = 0;
};

struct Record {
  std::span<const std::uint8_t> payload;
  std::uint64_t class_hash = 0;
};

struct Entry {
  std::size_t raven_index = 0;
  bool killed = false;
  std::uint32_t scalar_bits = 0;

  auto operator<=>(const Entry&) const = default;
};

struct CarrierParse {
  std::vector<Entry> entries;
  bool duplicate_state_key = false;
  bool invalid_chest_state = false;
};

struct RecordDecode {
  bool accepted = true;
  std::vector<Entry> entries;
  std::string reason;
};

template <typename T>
bool ReadLe(std::span<const std::uint8_t> bytes, std::size_t offset,
            T* value) {
  if (value == nullptr || offset > bytes.size() ||
      sizeof(T) > bytes.size() - offset) {
    return false;
  }
  T result = 0;
  for (std::size_t index = 0; index < sizeof(T); ++index) {
    result |= static_cast<T>(bytes[offset + index]) << (index * 8);
  }
  *value = result;
  return true;
}

bool ParseHeader(std::span<const std::uint8_t> bytes, Header* header) {
  if (header == nullptr || bytes.size() < 16) return false;
  std::array<std::uint16_t, 8> values{};
  for (std::size_t index = 0; index < values.size(); ++index) {
    if (!ReadLe(bytes, index * 2, &values[index])) return false;
  }
  *header = Header{values[0], values[1], values[2], values[3],
                   values[4], values[5], values[6], values[7]};
  return true;
}

std::string NormalWad(std::string_view value) {
  const std::size_t slash = value.find_last_of("\\/");
  const std::size_t start = slash == std::string_view::npos ? 0 : slash + 1;
  const std::size_t dot = value.find_last_of('.');
  const std::size_t end = dot == std::string_view::npos || dot < start
                              ? value.size()
                              : dot;
  std::string output(value.substr(start, end - start));
  std::transform(output.begin(), output.end(), output.begin(),
                 [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
  if (!output.empty()) output += ".wad";
  return output;
}

std::vector<std::uint8_t> AlignedBytes(
    std::span<const std::uint8_t> payload, std::size_t alignment) {
  if (alignment == 0) {
    return {payload.begin(), payload.end()};
  }
  if (payload.size() < 2) return {};
  std::vector<std::uint8_t> output(payload.size() - 1);
  for (std::size_t index = 0; index + 1 < payload.size(); ++index) {
    output[index] = static_cast<std::uint8_t>(
        static_cast<std::uint8_t>(payload[index] << alignment) |
        static_cast<std::uint8_t>(payload[index + 1] >> (8 - alignment)));
  }
  return output;
}

std::vector<std::uint8_t> WidthsForTag(std::uint8_t tag) {
  switch (tag) {
    case 0: return {2};
    case 1: return {5};
    case 2:
    case 3:
    case 5: return {3};
    case 4: return {2, 3, 5};
    default: return {};
  }
}

struct TokenWork {
  std::size_t position = 0;
  std::size_t index = 0;
  std::vector<Token> tokens;
};

bool ParseTokenPaths(std::span<const std::uint8_t> bytes, std::size_t start,
                     std::size_t count,
                     std::vector<std::vector<Token>>* paths,
                     std::string* reason) {
  if (paths == nullptr || count > kMaxTokenCount) {
    if (reason != nullptr) *reason = "token_count_cap";
    return false;
  }
  std::vector<TokenWork> stack;
  stack.push_back(TokenWork{start, 0, {}});
  std::size_t steps = 0;
  while (!stack.empty()) {
    if (++steps > kMaxParseSteps) {
      if (reason != nullptr) *reason = "token_parse_work_cap";
      return false;
    }
    TokenWork work = std::move(stack.back());
    stack.pop_back();
    if (work.index == count) {
      paths->push_back(std::move(work.tokens));
      if (paths->size() > kMaxParsePaths) {
        if (reason != nullptr) *reason = "token_parse_path_cap";
        return false;
      }
      continue;
    }
    if (work.position >= bytes.size()) continue;
    const std::uint8_t tag = bytes[work.position];
    std::vector<std::uint8_t> widths = WidthsForTag(tag);
    for (auto width_it = widths.rbegin(); width_it != widths.rend(); ++width_it) {
      const std::size_t width = *width_it;
      if (width > bytes.size() - work.position) continue;
      std::uint32_t payload = 0;
      for (std::size_t byte_index = 1; byte_index < width; ++byte_index) {
        payload |= static_cast<std::uint32_t>(
                       bytes[work.position + byte_index])
                   << ((byte_index - 1) * 8);
      }
      TokenWork next = work;
      next.position += width;
      ++next.index;
      next.tokens.push_back(Token{tag, payload,
                                  static_cast<std::uint8_t>(width)});
      stack.push_back(std::move(next));
    }
  }
  return true;
}

std::optional<std::size_t> MatchRaven(std::uint64_t registry_hash,
                                      std::uint64_t object_hash) {
  for (std::size_t index = 0; index < kRavenCatalogue.size(); ++index) {
    if (kRavenCatalogue[index].registry_hash == registry_hash &&
        kRavenCatalogue[index].object_hash == object_hash) {
      return index;
    }
  }
  return std::nullopt;
}

std::optional<std::size_t> TableIndex(const Token& token,
                                      std::size_t row_count) {
  if (token.tag != 3 || token.payload == 0 || token.payload > row_count) {
    return std::nullopt;
  }
  return static_cast<std::size_t>(token.payload - 1);
}

std::vector<CarrierParse> ParseCarrier(std::span<const std::uint8_t> raw,
                                       std::string* reason,
                                       std::span<const NumericStateIdentity> chests = {},
                                       std::uint8_t maximum_state = 4) {
  Header header{};
  if (!ParseHeader(raw, &header) ||
      header.pair_count > kMaxTokenCount ||
      header.row_count > kMaxTokenCount ||
      header.record_count > kMaxTokenCount) {
    return {};
  }
  const std::size_t decoded_size =
      static_cast<std::size_t>(header.blob_offset) + header.blob_length;
  const std::size_t compressed_end = 16 + header.compressed_length;
  if (decoded_size == 0 || compressed_end > raw.size()) return {};
  std::vector<std::uint8_t> decoded(decoded_size);
  uLongf output_length = static_cast<uLongf>(decoded.size());
  uLong source_length = header.compressed_length;
  const int zlib_result = uncompress2(
      decoded.data(), &output_length, raw.data() + 16, &source_length);
  if (zlib_result != Z_OK || output_length != decoded.size() ||
      source_length != header.compressed_length) {
    return {};
  }
  const std::size_t section0_end =
      compressed_end + static_cast<std::size_t>(header.section0_count) * 2;
  if (section0_end > raw.size() || header.blob_offset > decoded.size()) {
    return {};
  }
  std::vector<std::string> strings;
  strings.reserve(header.section0_count);
  for (std::size_t index = 0; index < header.section0_count; ++index) {
    std::uint16_t offset = 0;
    if (!ReadLe(raw, compressed_end + index * 2, &offset) ||
        offset >= header.blob_offset) {
      return {};
    }
    const auto begin = decoded.begin() + offset;
    const auto limit = decoded.begin() + header.blob_offset;
    const auto end = std::find(begin, limit, std::uint8_t{0});
    if (end == limit) return {};
    strings.emplace_back(begin, end);
  }

  std::vector<std::vector<Token>> token_paths;
  if (!ParseTokenPaths(raw, section0_end,
                       static_cast<std::size_t>(header.pair_count) * 2,
                       &token_paths, reason)) {
    return {};
  }
  std::vector<CarrierParse> parses;
  for (const std::vector<Token>& tokens : token_paths) {
    std::size_t metadata_end = section0_end;
    for (const Token& token : tokens) metadata_end += token.width;
    const std::size_t fixed_length =
        static_cast<std::size_t>(header.record_count) * 3 +
        static_cast<std::size_t>(header.row_count) * 6;
    if (metadata_end > raw.size() || fixed_length != raw.size() - metadata_end) {
      continue;
    }
    const std::size_t sizes_start = metadata_end;
    const std::size_t offsets_start = sizes_start + header.record_count;
    const std::size_t rows_start =
        offsets_start + static_cast<std::size_t>(header.record_count) * 2;
    const std::span<const std::uint8_t> blob(
        decoded.data() + header.blob_offset, header.blob_length);
    std::vector<Record> records;
    records.reserve(header.record_count);
    bool records_ok = true;
    for (std::size_t index = 0; index < header.record_count; ++index) {
      const std::size_t size = raw[sizes_start + index];
      std::uint16_t offset = 0;
      if (!ReadLe(raw, offsets_start + index * 2, &offset) || size < 8 ||
          offset > blob.size() || size > blob.size() - offset) {
        records_ok = false;
        break;
      }
      std::uint64_t class_hash = 0;
      if (!ReadLe(blob, offset, &class_hash)) { records_ok = false; break; }
      records.push_back(Record{blob.subspan(offset + 8, size - 8), class_hash});
    }
    if (!records_ok) continue;
    std::vector<Row> rows;
    rows.reserve(header.row_count);
    bool rows_ok = true;
    for (std::size_t index = 0; index < header.row_count; ++index) {
      std::uint16_t first = 0;
      std::uint16_t count = 0;
      if (!ReadLe(raw, rows_start + index * 6, &first) ||
          !ReadLe(raw, rows_start + index * 6 + 2, &count) ||
          first > header.pair_count || count > header.pair_count - first) {
        rows_ok = false;
        break;
      }
      rows.push_back(Row{first, count});
    }
    if (!rows_ok) continue;

    bool graph_ok = true;
    for (const Token& token : tokens) {
      if ((token.tag == 0 && token.payload > 1) ||
          (token.tag == 2 && token.payload >= strings.size()) ||
          (token.tag == 3 &&
           (token.payload == 0 || token.payload > rows.size())) ||
          (token.tag == 5 && token.payload >= records.size())) {
        graph_ok = false;
        break;
      }
    }
    if (!graph_ok) continue;
    const auto pair_tokens = [&tokens](std::size_t pair_index)
        -> std::pair<const Token&, const Token&> {
      return {tokens[pair_index * 2], tokens[pair_index * 2 + 1]};
    };
    const auto string_value = [&strings](const Token& token)
        -> std::optional<std::string_view> {
      if (token.tag != 2 || token.payload >= strings.size()) return std::nullopt;
      return strings[token.payload];
    };
    CarrierParse parsed;
    std::set<std::size_t> subobject_rows;
    for (std::size_t row_index = 0; row_index < rows.size(); ++row_index) {
      const Row& row = rows[row_index];
      std::size_t subobject_keys = 0;
      for (std::size_t pair = row.first_pair;
           pair < static_cast<std::size_t>(row.first_pair) + row.pair_count;
           ++pair) {
        const auto [key, value] = pair_tokens(pair);
        if (string_value(key) == "__subobjs") {
          ++subobject_keys;
          const auto table = TableIndex(value, rows.size());
          if (table.has_value()) subobject_rows.insert(*table);
        }
      }
      if (!chests.empty() && subobject_keys > 1) parsed.duplicate_state_key = true;
    }

    for (const std::size_t subobject_row : subobject_rows) {
      const Row& row = rows[subobject_row];
      for (std::size_t pair = row.first_pair;
           pair < static_cast<std::size_t>(row.first_pair) + row.pair_count;
           ++pair) {
        const auto [key, value] = pair_tokens(pair);
        const auto state_row = TableIndex(value, rows.size());
        if (!state_row.has_value()) continue;
        if (!chests.empty()) {
          if (key.tag != 5 || key.payload >= records.size()) continue;
          const Record& saved = records[key.payload];
          std::uint64_t registry = 0, object = 0;
          if (saved.payload.size() < 17 ||
              !ReadLe(saved.payload, 1, &registry) ||
              !ReadLe(saved.payload, 9, &object)) continue;
          const auto match = std::find_if(chests.begin(), chests.end(),
              [registry, object](const ChestIdentity& identity) {
                return identity.registry_hash == registry &&
                       identity.object_hash == object;
              });
          if (match == chests.end()) continue;
          if (saved.class_hash != UINT64_C(0x75E050AB149B4062) ||
              saved.payload.size() != 17 || saved.payload[0] != 1) {
            parsed.invalid_chest_state = true;
            continue;
          }
          std::size_t state_keys = 0;
          std::optional<std::uint32_t> scalar;
          const Row& state = rows[*state_row];
          for (std::size_t p = state.first_pair;
               p < static_cast<std::size_t>(state.first_pair) + state.pair_count;
               ++p) {
            const auto [field, value_token] = pair_tokens(p);
            if (string_value(field) != "state") continue;
            ++state_keys;
            if (value_token.tag == 1 && value_token.width == 5 &&
                (value_token.payload == 0x3F800000 ||
                 value_token.payload == 0x40000000 ||
                 value_token.payload == 0x40400000 ||
                 (maximum_state == 4 && value_token.payload == 0x40800000))) scalar = value_token.payload;
            else parsed.invalid_chest_state = true;
          }
          if (state_keys > 1) parsed.duplicate_state_key = true;
          if (scalar.has_value()) parsed.entries.push_back(Entry{
              static_cast<std::size_t>(match - chests.begin()), false, *scalar});
          continue;
        }
        std::optional<bool> killed;
        std::size_t killed_key_count = 0;
        const Row& state = rows[*state_row];
        for (std::size_t state_pair = state.first_pair;
             state_pair < static_cast<std::size_t>(state.first_pair) +
                              state.pair_count;
             ++state_pair) {
          const auto [state_key, state_value] = pair_tokens(state_pair);
          if (string_value(state_key) == "ravenKilled") {
            ++killed_key_count;
            if (state_value.tag == 0) killed = state_value.payload != 0;
          }
        }
        if (killed_key_count > 1) parsed.duplicate_state_key = true;
        if (!killed.has_value() || key.tag != 5 ||
            key.payload >= records.size()) {
          continue;
        }
        const std::span<const std::uint8_t> payload = records[key.payload].payload;
        if (payload.empty()) continue;
        const std::uint8_t flags = payload[0];
        const bool present = (flags & 1) != 0;
        const bool has_upper = (flags & 4) != 0;
        const std::size_t expected = 1 + (present ? 16 : 0) +
                                     (present && has_upper ? 4 : 0);
        if (!present || payload.size() != expected) continue;
        std::uint64_t registry_hash = 0;
        std::uint64_t object_hash = 0;
        if (!ReadLe(payload, 1, &registry_hash) ||
            !ReadLe(payload, 9, &object_hash)) {
          continue;
        }
        const auto raven = MatchRaven(registry_hash, object_hash);
        if (raven.has_value()) parsed.entries.push_back(Entry{*raven, *killed});
      }
    }
    std::sort(parsed.entries.begin(), parsed.entries.end());
    const auto duplicate = std::adjacent_find(
        parsed.entries.begin(), parsed.entries.end(),
        [](const Entry& left, const Entry& right) {
          return left.raven_index == right.raven_index;
        });
    if (duplicate != parsed.entries.end()) parsed.duplicate_state_key = true;
    parses.push_back(std::move(parsed));
  }
  std::sort(parses.begin(), parses.end(),
            [](const CarrierParse& left, const CarrierParse& right) {
              return left.entries < right.entries;
            });
  parses.erase(std::unique(parses.begin(), parses.end(),
                           [](const CarrierParse& left,
                              const CarrierParse& right) {
                             return left.entries == right.entries &&
                                    left.duplicate_state_key ==
                                        right.duplicate_state_key &&
                                    left.invalid_chest_state == right.invalid_chest_state;
                           }),
               parses.end());
  return parses;
}

RecordDecode DecodeRecord(const StagedRecordInput& record,
                          std::span<const NumericStateIdentity> chests = {},
                          std::uint8_t maximum_state = 4) {
  RecordDecode result;
  if (!chests.empty() && record.expected_lua_length != 0 &&
      (record.envelope.size() < 2 || record.expected_lua_length > kMaxCarrierBytes)) {
    result.accepted = false;
    result.reason = "invalid_chest_carrier_length";
    return result;
  }
  if (record.envelope.size() < 2 || record.expected_lua_length == 0) {
    return result;
  }
  std::uint16_t declared = 0;
  if (!ReadLe(std::span(record.envelope), 0, &declared) ||
      declared != record.envelope.size() - 2) {
    result.accepted = false;
    result.reason = "outer_length_mismatch";
    return result;
  }
  const auto payload = std::span(record.envelope).subspan(2);
  std::vector<CarrierParse> candidates;
  std::size_t candidate_count = 0;
  for (std::size_t alignment = 0; alignment < 8; ++alignment) {
    const std::vector<std::uint8_t> aligned = AlignedBytes(payload, alignment);
    std::size_t positions = 0;
    for (std::size_t position = 0; position + 2 <= aligned.size(); ++position) {
      if (aligned[position] !=
              static_cast<std::uint8_t>(record.expected_lua_length >> 8) ||
          aligned[position + 1] !=
              static_cast<std::uint8_t>(record.expected_lua_length & 0xff)) {
        continue;
      }
      if (++positions > kMaxLengthPositions) {
        result.accepted = false;
        result.reason = "lua_length_position_cap";
        return result;
      }
      const std::size_t start = position + 2;
      const std::size_t length = record.expected_lua_length;
      if (length < 18 || length > kMaxCarrierBytes || start > aligned.size() ||
          length > aligned.size() - start) {
        continue;
      }
      std::string parse_reason;
      std::vector<CarrierParse> parses = ParseCarrier(
          std::span(aligned).subspan(start, length), &parse_reason, chests, maximum_state);
      if (!parse_reason.empty()) {
        result.accepted = false;
        result.reason = parse_reason;
        return result;
      }
      for (CarrierParse& parse : parses) {
        if (parse.invalid_chest_state) {
          result.accepted = false;
          result.reason = "invalid_chest_state";
          return result;
        }
        ++candidate_count;
        if (candidate_count > kMaxCandidates || parse.duplicate_state_key) {
          result.accepted = false;
          result.reason = candidate_count > kMaxCandidates
                              ? "candidate_count_cap"
                              : "duplicate_state_key";
          return result;
        }
        candidates.push_back(std::move(parse));
      }
    }
  }
  std::sort(candidates.begin(), candidates.end(),
            [](const CarrierParse& left, const CarrierParse& right) {
              return left.entries < right.entries;
            });
  candidates.erase(std::unique(candidates.begin(), candidates.end(),
                               [](const CarrierParse& left,
                                  const CarrierParse& right) {
                                 return left.entries == right.entries;
                               }),
                   candidates.end());
  if (candidates.size() > 1) {
    result.accepted = false;
    result.reason = "multiple_graph_parses";
    return result;
  }
  if (!candidates.empty()) result.entries = std::move(candidates[0].entries);
  if (!chests.empty() && candidates.empty()) {
    result.accepted = false;
    result.reason = "no_chest_carrier_parse";
  }
  return result;
}

}  // namespace

DecodedNumericStateSnapshot DecodeNumericStateSnapshot(
    std::span<const StagedRecordInput> records,
    std::span<const NumericStateIdentity> identities,
    std::uint8_t maximum_state) {
  DecodedNumericStateSnapshot result;
  result.states.assign(identities.size(), 0);
  if ((maximum_state != 3 && maximum_state != 4) || identities.empty() ||
      identities.size() > 512 || records.size() > 4096) {
    result.reason = "chest_input_count_invalid";
    return result;
  }
  std::set<std::string_view> ids;
  std::set<std::pair<std::uint64_t, std::uint64_t>> keys;
  for (const auto& identity : identities) {
    if (identity.catalogue_id.empty() || NormalWad(identity.wad).empty() ||
        !ids.insert(identity.catalogue_id).second ||
        !keys.emplace(identity.registry_hash, identity.object_hash).second) {
      result.reason = "chest_identity_invalid";
      return result;
    }
  }
  std::vector<std::optional<std::uint32_t>> values(identities.size());
  for (const auto& record : records) {
    const auto decoded = DecodeRecord(record, identities, maximum_state);
    if (!decoded.accepted) {
      result.reason = "record_rejected:" + record.name + ":" + decoded.reason;
      return result;
    }
    for (const auto& entry : decoded.entries) {
      const auto index = entry.raven_index;
      if (NormalWad(record.name) != NormalWad(identities[index].wad)) {
        result.reason = "chest_wad_mismatch";
        return result;
      }
      if (values[index].has_value() && *values[index] != entry.scalar_bits) {
        result.reason = "conflicting_chest_state";
        return result;
      }
      values[index] = entry.scalar_bits;
    }
  }
  for (std::size_t i = 0; i < identities.size(); ++i) {
    if (!values[i].has_value()) continue;
    switch (*values[i]) {
      case 0x3F800000: result.states[i] = 1; break;
      case 0x40000000: result.states[i] = 2; break;
      case 0x40400000: result.states[i] = 3; break;
      case 0x40800000: result.states[i] = 4; break;
    }
  }
  result.accepted = true;
  result.reason = std::find(result.states.begin(), result.states.end(), 0) ==
      result.states.end() ? "accepted" : "accepted_partial";
  return result;
}

DecodedChestSnapshot DecodeStandardChestSnapshot(
    std::span<const StagedRecordInput> records,
    std::span<const ChestIdentity> identities) {
  const auto decoded = DecodeNumericStateSnapshot(records, identities, 4);
  DecodedChestSnapshot result;
  result.states.assign(identities.size(), ChestState::Unknown);
  result.unknown_count = identities.size();
  result.reason = decoded.reason;
  if (!decoded.accepted) return result;
  for (std::size_t i = 0; i < decoded.states.size(); ++i) {
    result.states[i] = static_cast<ChestState>(decoded.states[i]);
    if (result.states[i] == ChestState::Unknown) continue;
    --result.unknown_count;
    if (result.states[i] == ChestState::Opened) ++result.opened_count;
    else ++result.remaining_count;
  }
  result.accepted = true;
  return result;
}

DecodedRavenSnapshot DecodeRavenSnapshot(
    std::span<const StagedRecordInput> records) {
  DecodedRavenSnapshot result;
  std::set<std::string> staged_wads;
  std::array<std::optional<bool>, 53> explicit_states{};
  for (const StagedRecordInput& record : records) {
    const std::string wad = NormalWad(record.name);
    if (!wad.empty()) staged_wads.insert(wad);
    const RecordDecode decoded = DecodeRecord(record);
    if (!decoded.accepted) {
      result.reason = "record_rejected:" + record.name + ":" + decoded.reason;
      return result;
    }
    for (const Entry& entry : decoded.entries) {
      if (explicit_states[entry.raven_index].has_value() &&
          explicit_states[entry.raven_index] != entry.killed) {
        result.reason = "conflicting_raven_state:" +
                        std::string(kRavenCatalogue[entry.raven_index].catalogue_id);
        return result;
      }
      explicit_states[entry.raven_index] = entry.killed;
    }
  }
  std::string first_unknown;
  result.unknown_count = 0;
  for (std::size_t index = 0; index < kRavenCatalogue.size(); ++index) {
    if (explicit_states[index].has_value()) {
      result.killed[index] = *explicit_states[index];
      result.known[index] = true;
      result.explicit_state[index] = true;
      ++result.explicit_count;
    } else if (!staged_wads.contains(std::string(kRavenCatalogue[index].wad))) {
      result.killed[index] = false;
      result.known[index] = true;
      ++result.absence_default_false_count;
    } else {
      ++result.unknown_count;
      if (first_unknown.empty()) {
        first_unknown = std::string(kRavenCatalogue[index].catalogue_id);
      }
      continue;
    }
    if (result.killed[index]) ++result.killed_count;
  }
  result.alive_count =
      static_cast<std::uint32_t>(result.explicit_count +
                                 result.absence_default_false_count) -
      result.killed_count;
  if (result.unknown_count != 0) {
    result.reason = "present_wad_without_exact_state:" + first_unknown;
    return result;
  }
  if (result.explicit_count + result.absence_default_false_count !=
      kRavenCatalogue.size()) {
    result.reason = "snapshot_count_not_53";
    return result;
  }
  result.alive_count =
      static_cast<std::uint32_t>(kRavenCatalogue.size()) - result.killed_count;
  result.accepted = true;
  result.reason = "accepted";
  return result;
}

}  // namespace completionist
