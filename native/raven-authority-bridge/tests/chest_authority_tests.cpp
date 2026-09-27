#include <iostream>

#include "chest_authority.h"
#include "legendary_catalogue.generated.h"
#include "raven_fixture.generated.h"
#include <zlib.h>

#include <algorithm>
#include <array>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

using namespace completionist;
namespace {
using Bytes = std::vector<std::uint8_t>;
constexpr ChestIdentity kChest{"chest_a", "area.wad", 0x1234, 0x5678};
constexpr std::array kOne{kChest};
constexpr std::uint64_t kGameObjectClass = 0x75E050AB149B4062;

void Check(bool pass, const char* message) {
  if (!pass) throw std::runtime_error(message);
}
template <typename T> void Le(Bytes& bytes, T value) {
  for (std::size_t i = 0; i < sizeof(T); ++i)
    bytes.push_back(static_cast<std::uint8_t>(value >> (i * 8)));
}
void Token(Bytes& bytes, std::uint8_t tag, std::uint32_t value,
           std::size_t width) {
  bytes.push_back(tag);
  for (std::size_t i = 1; i < width; ++i)
    bytes.push_back(static_cast<std::uint8_t>(value >> ((i - 1) * 8)));
}
StagedRecordInput Carrier(std::uint32_t bits = 0x40800000,
                          bool duplicate = false, std::uint8_t tag = 1,
                          std::uint64_t klass = kGameObjectClass,
                          std::uint64_t object = kChest.object_hash,
                          std::string field = "state", std::uint8_t flags = 1,
                          bool duplicate_subobjects = false) {
  Bytes body{'_','_','s','u','b','o','b','j','s',0};
  body.insert(body.end(), field.begin(), field.end());
  body.push_back(0);
  const auto blob_offset = static_cast<std::uint16_t>(body.size());
  Le(body, klass);
  body.push_back(flags);
  Le(body, kChest.registry_hash);
  Le(body, object);
  uLongf compressed_size = compressBound(static_cast<uLong>(body.size()));
  Bytes compressed(compressed_size);
  Check(compress2(compressed.data(), &compressed_size, body.data(),
                  static_cast<uLong>(body.size()), Z_BEST_SPEED) == Z_OK,
        "fixture compression failed");
  compressed.resize(compressed_size);
  const auto pair_count = static_cast<std::uint16_t>(
      3 + (duplicate ? 1 : 0) + (duplicate_subobjects ? 1 : 0));
  Bytes raw;
  for (std::uint16_t value : std::array<std::uint16_t, 8>{
         2, blob_offset, pair_count, 3, 1, 25, 0,
         static_cast<std::uint16_t>(compressed_size)}) Le(raw, value);
  raw.insert(raw.end(), compressed.begin(), compressed.end());
  Le(raw, std::uint16_t{0}); Le(raw, std::uint16_t{10});
  Token(raw, 2, 0, 3); Token(raw, 3, 2, 3);
  if (duplicate_subobjects) { Token(raw, 2, 0, 3); Token(raw, 3, 2, 3); }
  Token(raw, 5, 0, 3); Token(raw, 3, 3, 3);
  for (int i = 0; i < (duplicate ? 2 : 1); ++i) {
    Token(raw, 2, 1, 3); Token(raw, tag, bits, tag == 0 ? 2 : 5);
  }
  raw.push_back(25); Le(raw, std::uint16_t{0});
  for (std::uint16_t i = 0; i < 3; ++i) {
    Le(raw, static_cast<std::uint16_t>(i + (duplicate_subobjects && i > 0 ? 1 : 0)));
    Le(raw, static_cast<std::uint16_t>(
        (i == 0 && duplicate_subobjects) || (i == 2 && duplicate) ? 2 : 1));
    Le(raw, std::uint16_t{0});
  }
  Bytes envelope;
  Le(envelope, static_cast<std::uint16_t>(raw.size() + 2));
  envelope.push_back(static_cast<std::uint8_t>(raw.size() >> 8));
  envelope.push_back(static_cast<std::uint8_t>(raw.size()));
  envelope.insert(envelope.end(), raw.begin(), raw.end());
  return {"area", static_cast<std::uint32_t>(raw.size()), envelope};
}
DecodedChestSnapshot Decode(const StagedRecordInput& record) {
  return DecodeStandardChestSnapshot(std::array{record}, kOne);
}
void Rejected(const DecodedChestSnapshot& snapshot) {
  Check(!snapshot.accepted, "invalid snapshot accepted");
  Check(snapshot.opened_count == 0 && snapshot.remaining_count == 0,
        "rejected snapshot leaked known counts");
  Check(std::all_of(snapshot.states.begin(), snapshot.states.end(),
                   [](auto state) { return state == ChestState::Unknown; }),
        "rejected snapshot leaked known state");
}
std::vector<StagedRecordInput> Replay() {
  std::vector<StagedRecordInput> records;
  for (const auto& fixture : kFixtureRecords) {
    const auto file = std::filesystem::path(COMPLETIONIST_FIXTURE_ROOT) /
                      fixture.relative_path;
    std::ifstream input(file, std::ios::binary);
    Check(input.good(), "archived carrier missing");
    Bytes bytes{std::istreambuf_iterator<char>(input),
                std::istreambuf_iterator<char>()};
    records.push_back({std::string(fixture.name), fixture.expected_lua_length,
                       std::move(bytes)});
  }
  return records;
}
}  // namespace

int main() {
  int cases = 0;
  try {
    for (const auto [bits, state] : std::array{
           std::pair{0x3F800000u, ChestState::Enabled},
           std::pair{0x40000000u, ChestState::Disabled},
           std::pair{0x40400000u, ChestState::Locked},
           std::pair{0x40800000u, ChestState::Opened}}) {
      const auto result = Decode(Carrier(bits));
      Check(result.accepted && result.states[0] == state, "enum decode differs");
      Check(result.opened_count == (state == ChestState::Opened ? 1u : 0u),
            "opened count differs");
      ++cases;
    }
    for (const auto [bits, state] : std::array{
           std::pair{0x3F800000u, std::uint8_t{1}},
           std::pair{0x40000000u, std::uint8_t{2}},
           std::pair{0x40400000u, std::uint8_t{3}}}) {
      const auto result = DecodeNumericStateSnapshot(std::array{Carrier(bits)}, kOne, 3);
      Check(result.accepted && result.states[0] == state, "artefact enum decode differs");
      ++cases;
    }
    const auto artefact_chest_enum = DecodeNumericStateSnapshot(
        std::array{Carrier(0x40800000)}, kOne, 3);
    Check(!artefact_chest_enum.accepted && artefact_chest_enum.states[0] == 0,
          "chest opened enum accepted as artefact acquired"); ++cases;
    for (const auto record : {
           Carrier(0x40400000, false, 1, kGameObjectClass, 999),
           Carrier(0x40400000, false, 1, 123, 999),
           Carrier(0x40400000, false, 1, kGameObjectClass,
                   kChest.object_hash, "ravenKilled")}) {
      const auto result = DecodeNumericStateSnapshot(std::array{record}, kOne, 3);
      Check(result.accepted && result.states[0] == 0,
            "unrelated owner or missing state hid artefact"); ++cases;
    }
    for (const auto record : {
           Carrier(0x40400000, false, 1, 123),
           Carrier(0x40A00000),
           Carrier(0x40400000, true),
           Carrier(0x40400000, false, 1, kGameObjectClass,
                   kChest.object_hash, "state", 5)}) {
      const auto result = DecodeNumericStateSnapshot(std::array{record}, kOne, 3);
      Check(!result.accepted && result.states[0] == 0,
            "bad artefact owner, enum, or field type accepted"); ++cases;
    }
    const auto partial_artefacts = DecodeNumericStateSnapshot(
        std::array{Carrier(0x40400000)},
        std::array{kChest, ChestIdentity{"chest_b", "other.wad", 0x1235, 0x5679}}, 3);
    Check(partial_artefacts.accepted && partial_artefacts.states[0] == 3 &&
          partial_artefacts.states[1] == 0,
          "absent artefact did not stay unknown"); ++cases;
    auto foreign_artefact = Carrier(0x40400000);
    foreign_artefact.name = "foreign.wad";
    const auto foreign = DecodeNumericStateSnapshot(std::array{foreign_artefact}, kOne, 3);
    Check(!foreign.accepted && foreign.states[0] == 0,
          "foreign WAD hid artefact"); ++cases;
    for (const auto bits : {0u, 0x40A00000u, 0x7FC00000u, 0x7F800000u,
                           4u, 0x3FC00000u}) {
      Rejected(Decode(Carrier(bits))); ++cases;
    }
    Rejected(Decode(Carrier(1, false, 0))); ++cases;
    Rejected(Decode(Carrier(0x40800000, true))); ++cases;
    Rejected(Decode(Carrier(0x40800000, false, 1, 123))); ++cases;
    Rejected(Decode(Carrier(0x40800000, false, 1, kGameObjectClass,
                            kChest.object_hash, "state", 5))); ++cases;
    Rejected(Decode(Carrier(0x40800000, false, 1, kGameObjectClass,
                            kChest.object_hash, "state", 1, true))); ++cases;
    const auto wrong_id = Decode(Carrier(0x40800000, false, 1,
                                         kGameObjectClass, 999));
    Check(wrong_id.accepted && wrong_id.unknown_count == 1,
          "unrelated object inferred chest state"); ++cases;
    const auto wrong_field = Decode(Carrier(0x40800000, false, 1,
                                            kGameObjectClass, kChest.object_hash,
                                            "ravenKilled"));
    Check(wrong_field.accepted && wrong_field.unknown_count == 1,
          "Raven field inferred chest state"); ++cases;
    auto wrong_wad = Carrier(); wrong_wad.name = "foreign.wad";
    Rejected(Decode(wrong_wad)); ++cases;
    auto case_wad = Carrier(); case_wad.name = "C:\\capture\\AREA.WAD";
    Check(Decode(case_wad).opened_count == 1, "WAD normalization differs"); ++cases;
    auto damaged = Carrier(); damaged.envelope.pop_back();
    Rejected(Decode(damaged)); ++cases;
    auto invalid = Carrier(); invalid.expected_lua_length = 0x4801;
    Rejected(Decode(invalid)); ++cases;
    auto no_parse = Carrier();
    std::fill(no_parse.envelope.begin() + 2, no_parse.envelope.end(), std::uint8_t{0});
    Rejected(Decode(no_parse)); ++cases;
    const auto missing = DecodeStandardChestSnapshot({}, kOne);
    Check(missing.accepted && missing.unknown_count == 1,
          "absent WAD became remaining chest"); ++cases;
    auto present = Carrier(); present.expected_lua_length = 0;
    Check(Decode(present).unknown_count == 1,
          "missing carrier became remaining chest"); ++cases;
    Rejected(DecodeStandardChestSnapshot(std::array{Carrier(), Carrier(0x3F800000)},
                                        kOne)); ++cases;
    Rejected(DecodeStandardChestSnapshot(std::array{Carrier()},
                                        std::array{kChest, kChest})); ++cases;
    const auto replay = DecodeStandardChestSnapshot(Replay(), kLegendaryCatalogue);
    Check(replay.accepted, replay.reason.c_str());
    std::cout << "REPLAY opened=" << replay.opened_count
              << " remaining=" << replay.remaining_count
              << " unknown=" << replay.unknown_count << '\n';
    for (std::size_t i = 0; i < replay.states.size(); ++i)
      if (replay.states[i] != kLegendaryFixtureStates[i])
        std::cerr << kLegendaryCatalogue[i].catalogue_id << " actual="
                  << static_cast<int>(replay.states[i]) << " expected="
                  << static_cast<int>(kLegendaryFixtureStates[i]) << '\n';
    Check(replay.states.size() == 33 && replay.opened_count == 23 &&
          replay.remaining_count == 9 && replay.unknown_count == 1,
          "archived current-33 replay counts differ");
    for (std::size_t i = 0; i < replay.states.size(); ++i)
      Check(replay.states[i] == kLegendaryFixtureStates[i],
            "exact per-object replay state differs");
    ++cases;

    ChestSessionAuthority session(1);
    Check(session.States()[0] == ChestState::Unknown, "bootstrap exposed state");
    Check(!session.Apply(Decode(Carrier()), 1, 1), "snapshot bypassed boundary");
    Check(session.BeginBoundary(10), "new boundary rejected");
    Check(!session.Apply(Decode(Carrier()), 9, 100), "old save accepted");
    Check(!session.Apply(Decode(Carrier()), 11, 100), "future save accepted");
    Check(session.Apply(Decode(Carrier(0x3F800000)), 10, 1), "fresh state rejected");
    Check(!session.Apply(Decode(Carrier()), 10, 1), "duplicate generation accepted");
    Check(!session.NoteOpened(1, 10) && !session.NoteOpened(0, 9),
          "wrong chest or epoch event accepted");
    Check(session.NoteOpened(0, 10), "exact opened event rejected");
    Check(session.Apply(Decode(Carrier(0x3F800000)), 10, 2), "new snapshot rejected");
    Check(session.States()[0] == ChestState::Opened, "same-save state revived chest");
    Check(session.BeginBoundary(11), "save switch rejected");
    Check(session.States()[0] == ChestState::Unknown, "old save leaked at boundary");
    Check(!session.Apply(Decode(Carrier()), 10, 999), "late old-save snapshot accepted");
    Check(session.Apply(Decode(Carrier(0x3F800000)), 11, 1), "older save did not revive");
    Check(session.States()[0] == ChestState::Enabled, "overlay crossed save boundary");
    Check(!session.BeginBoundary(10) && !session.BeginBoundary(11),
          "old/repeated boundary cleared state");
    Check(!session.Apply(Decode(damaged), 11, 2), "invalid frame applied");
    Check(session.States()[0] == ChestState::Enabled, "invalid frame changed state");
    auto wrong_shape = Decode(Carrier()); wrong_shape.states.clear();
    Check(!session.Apply(wrong_shape, 11, 2), "wrong shape applied");
    auto wrong_count = Decode(Carrier()); wrong_count.opened_count = 0;
    Check(!session.Apply(wrong_count, 11, 2), "wrong count applied");
    auto wrong_enum = Decode(Carrier()); wrong_enum.states[0] = static_cast<ChestState>(5);
    Check(!session.Apply(wrong_enum, 11, 2), "wrong enum applied");
    Check(session.States()[0] == ChestState::Enabled, "bad snapshot changed state");
    Check(session.Apply(missing, 11, 2), "fresh unknown state rejected");
    Check(session.States()[0] == ChestState::Unknown, "lost authority remained visible");
    Check(session.BeginBoundary(12), "restart boundary rejected");
    Check(session.Apply(Decode(Carrier()), 12, 1), "saved opened state rejected");
    Check(session.Apply(Decode(Carrier(0x3F800000)), 12, 2), "periodic frame rejected");
    Check(session.States()[0] == ChestState::Opened, "saved opened state revived in epoch");
    cases += 15;
    std::cout << "LEGENDARY_AUTHORITY_TESTS_PASSED cases=" << cases
              << " archived_opened=23 archived_remaining=9 archived_unknown=1\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FAIL: " << error.what() << '\n';
    return 1;
  }
}
