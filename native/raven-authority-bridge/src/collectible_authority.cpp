#include "collectible_authority.h"
#include "collectible_catalogue.generated.h"
#include <algorithm>
#include <set>

namespace completionist {
std::string CollectibleSnapshotResponse(std::span<const StagedRecordInput> records,
    std::uint64_t nonce, std::uint64_t restore_epoch, std::uint64_t generation) {
  constexpr auto unavailable = "COLLECTIBLE_SNAPSHOT_V1 UNAVAILABLE\n";
  std::vector<StagedRecordInput> relevant;
  std::set<std::string> seen;
  for (const auto& record : records) {
    auto wad = record.name;
    for (auto& ch : wad) if (ch >= 'A' && ch <= 'Z') ch += 'a' - 'A';
    if (!wad.ends_with(".wad")) wad += ".wad";
    const auto matches_wad = [&](const auto& row) { return row.wad == wad; };
    if (std::none_of(kCollectibleChests.begin(), kCollectibleChests.end(), matches_wad) &&
        std::none_of(kCollectibleArtefacts.begin(), kCollectibleArtefacts.end(), matches_wad)) continue;
    if (!seen.insert(wad).second) return unavailable;
    relevant.push_back(record);
  }
  const auto decoded = DecodeStandardChestSnapshot(relevant, kCollectibleChests);
  if (!decoded.accepted || decoded.states.size() != kCollectibleChests.size()) return unavailable;
  std::string states(kCollectibleCount, '0');
  for (std::size_t i = 0; i < decoded.states.size(); ++i) {
    const auto value = decoded.states[i];
    states[kCollectibleChestIndices[i]] = value == ChestState::Opened ? '2' :
        value == ChestState::Unknown ? '0' : '1';
  }
  const auto artefacts = DecodeNumericStateSnapshot(relevant, kCollectibleArtefacts, 3);
  if (!artefacts.accepted || artefacts.states.size() != kCollectibleArtefacts.size()) return unavailable;
  for (std::size_t i = 0; i < artefacts.states.size(); ++i) {
    const auto value = artefacts.states[i];
    states[kCollectibleArtefactIndices[i]] = value == 3 ? '2' : value == 0 ? '0' : '1';
  }
  return "COLLECTIBLE_SNAPSHOT_V1 nonce=" + std::to_string(nonce) +
      " restoreEpoch=" + std::to_string(restore_epoch) +
      " contract=" + kCollectibleContract + " generation=" + std::to_string(generation) +
      " states=" + states + "\n";
}
}
