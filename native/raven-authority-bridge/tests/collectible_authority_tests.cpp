#include "collectible_authority.h"
#include "collectible_catalogue.generated.h"
#include "raven_fixture.generated.h"
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
using namespace completionist;
void Check(bool pass, const char* reason) { if (!pass) throw std::runtime_error(reason); }
int main() {
  try {
    std::vector<StagedRecordInput> records;
    for (const auto& fixture : kFixtureRecords) {
      std::ifstream input(std::filesystem::path(COMPLETIONIST_FIXTURE_ROOT) / fixture.relative_path,
                          std::ios::binary);
      Check(input.good(), "missing fixture");
      std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(input), {}};
      records.push_back({std::string(fixture.name), fixture.expected_lua_length, std::move(bytes)});
    }
    const auto wire = CollectibleSnapshotResponse(records, 7, 12, 3);
    Check(wire.starts_with("COLLECTIBLE_SNAPSHOT_V1 nonce=7 restoreEpoch=12 contract="), "lost response identity");
    Check(wire.find(kCollectibleContract) != std::string::npos, "wrong contract");
    const auto start = wire.find(" generation=3 states=");
    Check(start != std::string::npos, "lost generation");
    const auto states = wire.substr(wire.find("states=") + 7, kCollectibleCount);
    Check(states.size() == 410 && wire.ends_with("\n") && wire.size() < 4096, "unbounded wire");
    std::size_t chest_collected = 0, chest_remaining = 0, chest_unknown = 0;
    for (const auto index : kCollectibleChestIndices) {
      chest_collected += states[index] == '2';
      chest_remaining += states[index] == '1';
      chest_unknown += states[index] == '0';
    }
    Check(chest_collected == 23 && chest_remaining == 9 && chest_unknown == 1,
          "archived chest family counts differ");
    std::size_t artefact_collected = 0, artefact_remaining = 0, artefact_unknown = 0;
    for (std::size_t i = 0; i < kCollectibleArtefactIndices.size(); ++i) {
      const auto state = states[kCollectibleArtefactIndices[i]];
      const auto expected = kCollectibleArtefactFixtureStates[i] == 3 ? '2' : '1';
      Check(state == expected, "exact archived artefact state differs");
      artefact_collected += state == '2';
      artefact_remaining += state == '1';
      artefact_unknown += state == '0';
    }
    Check(artefact_collected == 38 && artefact_remaining == 7 && artefact_unknown == 0,
          "archived artefact family counts differ");
    Check(std::count(states.begin(), states.end(), '2') == 61 &&
          std::count(states.begin(), states.end(), '1') == 16 &&
          std::count(states.begin(), states.end(), '0') == 333,
          "archived total counts differ");
    for (std::size_t i=0; i<410; ++i) {
      if (std::find(kCollectibleChestIndices.begin(), kCollectibleChestIndices.end(), i) == kCollectibleChestIndices.end() &&
          std::find(kCollectibleArtefactIndices.begin(), kCollectibleArtefactIndices.end(), i) == kCollectibleArtefactIndices.end())
        Check(states[i] == '0', "state applied to unrelated catalogue ID");
    }
    const auto empty = CollectibleSnapshotResponse({}, 8, 13, 4);
    Check(empty.ends_with("states=" + std::string(410, '0') + "\n"), "absence must be unknown");
    const auto duplicate = std::find_if(records.begin(), records.end(), [](const auto& row) {
      return row.name == "Alf600_TempleInt" || row.name == "alf600_templeint";
    });
    Check(duplicate != records.end(), "fixture identity missing");
    records.push_back(*duplicate);
    Check(CollectibleSnapshotResponse(records, 9, 13, 5) == "COLLECTIBLE_SNAPSHOT_V1 UNAVAILABLE\n",
          "duplicate WAD accepted");
    std::cout << "COLLECTIBLE_NATIVE_TESTS_PASS chest=23/9/1 artefact=38/7/0 total=61/16/333\n";
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
