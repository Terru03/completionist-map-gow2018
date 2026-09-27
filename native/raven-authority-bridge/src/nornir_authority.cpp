#include "nornir_authority.h"
#include "nornir_catalogue.generated.h"
#include <algorithm>
#include <set>

namespace completionist {
DecodedChestSnapshot DecodeNornirSnapshot(std::span<const StagedRecordInput> records) {
  std::vector<StagedRecordInput> relevant;
  std::set<std::string> seen;
  for (const auto& record : records) {
    std::string wad = record.name;
    for (char& ch : wad) if (ch >= 'A' && ch <= 'Z') ch = static_cast<char>(ch + ('a' - 'A'));
    if (!wad.ends_with(".wad")) wad += ".wad";
    if (std::none_of(kNornirCatalogue.begin(), kNornirCatalogue.end(),
                    [&](const auto& row) { return row.wad == wad; })) continue;
    if (!seen.insert(wad).second) {
      DecodedChestSnapshot rejected;
      rejected.reason = "duplicate_staged_wad:" + wad;
      return rejected;
    }
    relevant.push_back(record);
  }
  return DecodeStandardChestSnapshot(relevant, kNornirCatalogue);
}

std::string NornirSnapshotResponse(const DecodedChestSnapshot& snapshot,
                                  std::uint64_t nonce, std::uint64_t restore_epoch) {
  if (!snapshot.accepted || snapshot.states.size() != kNornirCatalogue.size())
    return "NORNIR_SNAPSHOT_V1 UNAVAILABLE\n";
  std::string states;
  for (const auto state : snapshot.states) {
    const auto value = static_cast<unsigned>(state);
    if (value > 4) return "NORNIR_SNAPSHOT_V1 UNAVAILABLE\n";
    states.push_back(static_cast<char>('0' + value));
  }
  return "NORNIR_SNAPSHOT_V1 nonce=" + std::to_string(nonce) +
         " restoreEpoch=" + std::to_string(restore_epoch) +
         " contract=" + kNornirContract + " states=" + states + "\n";
}
}
