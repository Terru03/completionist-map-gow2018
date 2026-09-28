#include "nornir_authority.h"
#include "nornir_catalogue.generated.h"
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
      std::vector<std::uint8_t> data{std::istreambuf_iterator<char>(input), {}};
      records.push_back({std::string(fixture.name), fixture.expected_lua_length, std::move(data)});
    }
    auto snapshot = DecodeNornirSnapshot(records);
    if (!snapshot.accepted) throw std::runtime_error("Nornir decode rejected: " + snapshot.reason);
    Check(snapshot.accepted && snapshot.unknown_count == 1, "need 21 exact parent states");
    for (std::size_t i = 0; i < kNornirCatalogue.size(); ++i) {
      if (kNornirCatalogue[i].wad == "xpl950_beachmaze.wad")
        Check(snapshot.states[i] == ChestState::Disabled, "BeachMaze exact nested key");
      if (kNornirCatalogue[i].wad == "xpl100_httk.wad")
        Check(snapshot.states[i] == ChestState::Unknown, "absent WAD must stay unknown");
    }
    auto empty = DecodeNornirSnapshot({});
    Check(empty.accepted && empty.unknown_count == 22, "empty capture cannot imply remaining");
    Check(NornirSnapshotResponse(snapshot, 7, 3).find("nonce=7 restoreEpoch=3") != std::string::npos,
          "response context lost");
    Check(NornirSnapshotResponse({}, 7, 3) == "NORNIR_SNAPSHOT_V1 UNAVAILABLE\n", "failed capture leaked state");
    auto found = std::find_if(records.begin(), records.end(), [](const auto& row) {
      return row.name == "Xpl950_BeachMaze" || row.name == "xpl950_beachmaze";
    });
    Check(found != records.end(), "BeachMaze fixture missing");
    records.push_back(*found);
    Check(!DecodeNornirSnapshot(records).accepted, "duplicate WAD accepted");
    std::cout << "NORNIR_NATIVE_TESTS_PASS replay=21 unknown=1 absence_duplicate_wire_checked\n";
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
