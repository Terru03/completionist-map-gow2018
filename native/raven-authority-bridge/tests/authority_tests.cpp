#include <windows.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include "authority_decoder.h"
#include "authority_runtime.h"
#include "raven_catalogue.generated.h"
#include "raven_fixture.generated.h"
#include "snapshot_delivery.h"

namespace {

int Fail(const std::string& message) {
  std::cerr << "FAIL: " << message << '\n';
  return 1;
}

std::vector<std::uint8_t> ReadFile(const std::wstring& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) return {};
  return {std::istreambuf_iterator<char>(input),
          std::istreambuf_iterator<char>()};
}

}  // namespace

int wmain() {
  if (completionist::kRavenCatalogue.size() != 53) {
    return Fail("catalogue count not 53");
  }
  for (std::size_t left = 0; left < completionist::kRavenCatalogue.size();
       ++left) {
    for (std::size_t right = left + 1;
         right < completionist::kRavenCatalogue.size(); ++right) {
      const auto& a = completionist::kRavenCatalogue[left];
      const auto& b = completionist::kRavenCatalogue[right];
      if (a.catalogue_id == b.catalogue_id ||
          (a.registry_hash == b.registry_hash && a.object_hash == b.object_hash)) {
        return Fail("catalogue identity not unique");
      }
    }
  }

  const std::wstring root = COMPLETIONIST_FIXTURE_ROOT;
  std::vector<completionist::StagedRecordInput> records;
  records.reserve(completionist::kFixtureRecords.size());
  for (const auto& fixture : completionist::kFixtureRecords) {
    std::wstring relative(fixture.relative_path.begin(),
                          fixture.relative_path.end());
    std::replace(relative.begin(), relative.end(), L'/', L'\\');
    completionist::StagedRecordInput record;
    record.name = std::string(fixture.name);
    record.expected_lua_length = fixture.expected_lua_length;
    record.envelope = ReadFile(root + L"\\" + relative);
    if (record.envelope.empty()) {
      return Fail("fixture payload missing: " + std::string(fixture.relative_path));
    }
    records.push_back(std::move(record));
  }
  const completionist::DecodedRavenSnapshot decoded =
      completionist::DecodeRavenSnapshot(records);
  if (!decoded.accepted) return Fail("accepted replay rejected: " + decoded.reason);
  if (decoded.explicit_count != 42 ||
      decoded.absence_default_false_count != 11 ||
      decoded.killed_count != 27 || decoded.alive_count != 26) {
    return Fail("accepted replay counts differ");
  }
  for (std::size_t index = 0; index < completionist::kRavenCatalogue.size();
       ++index) {
    if (decoded.killed[index] !=
        completionist::kRavenCatalogue[index].fixture_killed) {
      return Fail("accepted replay state differs: " +
                  std::string(completionist::kRavenCatalogue[index].catalogue_id));
    }
  }
  auto state_for = [&decoded](std::string_view id) {
    for (std::size_t index = 0; index < completionist::kRavenCatalogue.size();
         ++index) {
      if (completionist::kRavenCatalogue[index].catalogue_id == id)
        return decoded.killed[index];
    }
    return false;
  };
  if (state_for("raven_642d0d164af0a5d4076e77933c549a5d") ||
      !state_for("raven_c945cb53465b58decfcbd4a221cb5326") ||
      !state_for("raven_e32f7bab42fd7298890f6aa56a734562")) {
    return Fail("Veithurgard false,true,true fixture differs");
  }

  completionist::SnapshotStore store;
  completionist::NativeRavenSnapshot first;
  first.killed.fill(false);
  first.alive_count = 53;
  completionist::NativeRavenSnapshot second;
  second.killed.fill(true);
  second.killed_count = 53;
  std::atomic<bool> stop{false};
  std::atomic<bool> torn{false};
  std::thread reader([&] {
    while (!stop.load()) {
      completionist::NativeRavenSnapshot value;
      if (!store.Read(&value)) continue;
      const bool all_false =
          std::all_of(value.killed.begin(), value.killed.end(),
                      [](bool item) { return !item; });
      const bool all_true =
          std::all_of(value.killed.begin(), value.killed.end(),
                      [](bool item) { return item; });
      if (!all_false && !all_true) torn.store(true);
    }
  });
  for (int index = 0; index < 2000; ++index) {
    store.Publish((index & 1) == 0 ? first : second);
  }
  stop.store(true);
  reader.join();
  if (torn.load()) return Fail("snapshot store exposed torn state");

  completionist::SnapshotStore freshness_store;
  completionist::NativeRavenSnapshot stable;
  stable.killed.fill(false);
  stable.alive_count = 53;
  freshness_store.Publish(stable);
  completionist::NativeRavenSnapshot freshness_first;
  if (!freshness_store.Read(&freshness_first)) {
    return Fail("freshness store first read unavailable");
  }
  freshness_store.Publish(stable);
  completionist::NativeRavenSnapshot freshness_second;
  if (!freshness_store.Read(&freshness_second) ||
      freshness_second.generation != freshness_first.generation + 1) {
    return Fail("identical accepted capture did not advance freshness generation");
  }

  completionist::NativeRavenSnapshot wire;
  wire.generation = 7;
  wire.captured_tick_ms = 1234;
  wire.alive_count = decoded.alive_count;
  wire.killed_count = decoded.killed_count;
  wire.explicit_count = decoded.explicit_count;
  wire.absence_default_false_count = decoded.absence_default_false_count;
  wire.killed = decoded.killed;
  const std::string response =
      completionist::BuildRavenSnapshotWireResponse(wire);
  if (!response.starts_with("RAVEN_SNAPSHOT_V1 schema=1 generation=7 ") ||
      response.find(" count=53 unknown=0 alive=26 killed=27 explicit=42 ") ==
          std::string::npos ||
      response.find("raven_c945cb53465b58decfcbd4a221cb5326") ==
          std::string::npos ||
      response.find("raven_642d0d164af0a5d4076e77933c549a5d") !=
          std::string::npos ||
      response.back() != '\n') {
    return Fail("Lua wire snapshot differs");
  }

  const std::string boundary_response =
      completionist::BuildRavenBoundarySnapshotWireResponse(wire, 42);
  if (!boundary_response.starts_with(
          "RAVEN_SNAPSHOT_V2 schema=2 boundaryEpoch=42 generation=7 ") ||
      boundary_response.find(
          " count=53 unknown=0 alive=26 killed=27 explicit=42 ") ==
          std::string::npos ||
      boundary_response.find(
          "raven_c945cb53465b58decfcbd4a221cb5326") ==
          std::string::npos ||
      boundary_response.back() != '\n') {
    return Fail("Lua boundary wire snapshot differs");
  }

  std::uint16_t bound_port = 0;
  int listener_error = 0;
  const std::uintptr_t first_listener =
      completionist::delivery_test::OpenLoopbackListener(
          0, &bound_port, &listener_error);
  if (first_listener == completionist::delivery_test::kInvalidListener ||
      bound_port == 0 || listener_error != 0) {
    return Fail("loopback listener did not bind exclusively");
  }
  const std::uintptr_t collision =
      completionist::delivery_test::OpenLoopbackListener(
          bound_port, nullptr, &listener_error);
  if (collision != completionist::delivery_test::kInvalidListener) {
    completionist::delivery_test::CloseLoopbackListener(collision);
    completionist::delivery_test::CloseLoopbackListener(first_listener);
    return Fail("loopback listener collision was not refused");
  }
  completionist::delivery_test::CloseLoopbackListener(first_listener);

  std::cout << "RAVEN_BRIDGE_AUTHORITY_TESTS_PASSED states=53 explicit=42 "
               "absentWadFalse=11 killed=27 alive=26 delivery=loopback "
               "collision_refused=true freshness_generation=true boundary_epoch_wire=true\n";
  return 0;
}
