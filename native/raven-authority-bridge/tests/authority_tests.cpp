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

  completionist::SnapshotPublicationGate bootstrap_gate;
  completionist::NativeRavenSnapshot bootstrap_zero;
  bootstrap_zero.killed.fill(false);
  bootstrap_zero.alive_count = 53;
  bootstrap_zero.killed_count = 0;
  bootstrap_zero.explicit_count = 0;
  bootstrap_zero.absence_default_false_count = 53;

  // Exact field regression from 2026-09-22: one startup 0/53 image was
  // followed one second later by a present-WAD ambiguity. The first image
  // must never be publishable.
  if (bootstrap_gate.Observe(bootstrap_zero, 1000)) {
    return Fail("first all-false bootstrap image was accepted");
  }
  bootstrap_gate.Reject();
  if (bootstrap_gate.Observe(bootstrap_zero, 3000)) {
    return Fail("all-false image after rejection bypassed quarantine");
  }
  if (bootstrap_gate.Observe(bootstrap_zero, 3499)) {
    return Fail("rapid all-false confirmation bypassed stability window");
  }
  if (!bootstrap_gate.Observe(bootstrap_zero, 4000)) {
    return Fail("stable all-false authority never confirmed");
  }
  if (!bootstrap_gate.Observe(bootstrap_zero, 4001)) {
    return Fail("confirmed all-false authority did not remain usable");
  }

  completionist::NativeRavenSnapshot nonzero = bootstrap_zero;
  nonzero.killed[0] = true;
  nonzero.alive_count = 52;
  nonzero.killed_count = 1;
  nonzero.explicit_count = 1;
  nonzero.absence_default_false_count = 52;
  bootstrap_gate.Reject();
  if (!bootstrap_gate.Observe(nonzero, 5000)) {
    return Fail("nonzero Raven authority was unnecessarily quarantined");
  }

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
  wire.known = decoded.known;
  wire.explicit_state = decoded.explicit_state;
  for (std::size_t index = 0; index < completionist::kRavenCatalogue.size();
       ++index) {
    wire.absence_default_state[index] =
        decoded.known[index] && !decoded.explicit_state[index];
  }
  wire.unknown_count = 0;
  completionist::delivery_test::ResetSessionAuthority();
  const std::string response =
      completionist::BuildRavenSnapshotWireResponse(wire, 0);
  if (!response.starts_with(
          "RAVEN_SNAPSHOT_V1 schema=1 restoreEpoch=0 generation=7 ") ||
      response.find(" count=53 unknown=0 alive=26 killed=27 explicit=42 ") ==
          std::string::npos ||
      response.find("raven_c945cb53465b58decfcbd4a221cb5326") ==
          std::string::npos ||
      response.find("raven_642d0d164af0a5d4076e77933c549a5d") !=
          std::string::npos ||
      response.back() != '\n') {
    return Fail("Lua wire snapshot differs");
  }

  completionist::NativeRavenSnapshot partial = wire;
  partial.partial_usable = true;
  partial.unknown_count = 1;
  partial.explicit_count = 41;
  partial.absence_default_false_count = 11;
  std::size_t partial_unknown_index = completionist::kRavenCatalogue.size();
  for (std::size_t index = 0; index < completionist::kRavenCatalogue.size();
       ++index) {
    if (completionist::kRavenCatalogue[index].catalogue_id ==
        "raven_642d0d164af0a5d4076e77933c549a5d") {
      partial_unknown_index = index;
      break;
    }
  }
  if (partial_unknown_index >= completionist::kRavenCatalogue.size() ||
      partial.killed[partial_unknown_index]) {
    return Fail("partial wire fixture Raven differs");
  }
  partial.known[partial_unknown_index] = false;
  partial.explicit_state[partial_unknown_index] = false;
  --partial.alive_count;
  const std::string partial_response =
      completionist::BuildRavenPartialSnapshotWireResponse(partial, 0);
  if (!partial_response.starts_with(
          "RAVEN_SNAPSHOT_V1 PARTIAL schema=1 restoreEpoch=0 ") ||
      partial_response.find(" unknown=1 alive=25 killed=27 explicit=41 ") ==
          std::string::npos ||
      partial_response.find(
          "unknownIds=raven_642d0d164af0a5d4076e77933c549a5d") ==
          std::string::npos ||
      partial_response.find(" absenceIds=-") != std::string::npos ||
      partial_response.back() != '\n') {
    return Fail("Lua partial wire snapshot differs");
  }
  const std::string partial_boundary_response =
      completionist::BuildRavenPartialBoundarySnapshotWireResponse(partial, 3);
  if (!partial_boundary_response.starts_with(
          "RAVEN_SNAPSHOT_V2 PARTIAL schema=2 boundaryEpoch=3 ")) {
    return Fail("Lua partial boundary wire snapshot differs");
  }

  // Session-only kill evidence augments, but never replaces, the decoded
  // authoritative saved set. A later restore epoch makes prior session notes
  // ineligible so an older checkpoint can legitimately revive that Raven.
  if (!completionist::delivery_test::NoteKilled(
          "raven_642d0d164af0a5d4076e77933c549a5d")) {
    return Fail("session kill note rejected known Raven");
  }
  const auto merged_partial_epoch0 =
      completionist::delivery_test::MergeCurrentEpochKills(partial);
  if (merged_partial_epoch0.unknown_count != 0 ||
      !merged_partial_epoch0.known[partial_unknown_index] ||
      !merged_partial_epoch0.killed[partial_unknown_index] ||
      merged_partial_epoch0.killed_count != 28 ||
      merged_partial_epoch0.alive_count != 25) {
    return Fail("session kill overlay did not resolve partial Raven");
  }
  const auto merged_epoch0 =
      completionist::delivery_test::MergeCurrentEpochKills(wire);
  if (merged_epoch0.killed_count != 28) {
    return Fail("session kill overlay count differs");
  }
  bool newly_killed_found = false;
  for (std::size_t index = 0; index < completionist::kRavenCatalogue.size();
       ++index) {
    if (completionist::kRavenCatalogue[index].catalogue_id ==
        "raven_642d0d164af0a5d4076e77933c549a5d") {
      newly_killed_found = merged_epoch0.killed[index];
      break;
    }
  }
  if (!newly_killed_found) return Fail("session kill overlay missing Raven");
  auto merged_state_for = [&merged_epoch0](std::string_view id) {
    for (std::size_t index = 0; index < completionist::kRavenCatalogue.size();
         ++index) {
      if (completionist::kRavenCatalogue[index].catalogue_id == id)
        return merged_epoch0.killed[index];
    }
    return false;
  };
  if (!merged_state_for("raven_c945cb53465b58decfcbd4a221cb5326") ||
      !merged_state_for("raven_e32f7bab42fd7298890f6aa56a734562")) {
    return Fail("saved kills disappeared from session overlay");
  }

  const std::uint64_t epoch1 =
      completionist::delivery_test::NoteRestoreBoundary(10000);
  const std::uint64_t epoch1_repeat =
      completionist::delivery_test::NoteRestoreBoundary(10100);
  if (epoch1 != 1 || epoch1_repeat != 1 ||
      completionist::delivery_test::CurrentRestoreEpoch() != 1) {
    return Fail("restore boundary coalescing differs");
  }
  const auto merged_epoch1 =
      completionist::delivery_test::MergeCurrentEpochKills(wire);
  if (merged_epoch1.killed_count != 27) {
    return Fail("prior-epoch session kill leaked across restore");
  }
  if (!completionist::delivery_test::NoteKilled(
          "raven_642d0d164af0a5d4076e77933c549a5d")) {
    return Fail("current-epoch session kill note rejected");
  }
  const auto merged_epoch1_kill =
      completionist::delivery_test::MergeCurrentEpochKills(wire);
  if (merged_epoch1_kill.killed_count != 28) {
    return Fail("current-epoch session kill not merged");
  }
  const std::uint64_t epoch2 =
      completionist::delivery_test::NoteRestoreBoundary(12000);
  if (epoch2 != 2 ||
      completionist::delivery_test::MergeCurrentEpochKills(wire).killed_count !=
          27) {
    return Fail("later restore did not drop session-only kill");
  }

  // A fresh/new-game transition does not necessarily call any Raven
  // OnRestoreCheckpoint. The raw saved authority is monotonic within one
  // playthrough: if a previously killed Raven becomes alive, that is
  // process-wide proof that a different save/checkpoint/new game was loaded.
  completionist::delivery_test::ResetSessionAuthority();
  if (completionist::delivery_test::ObserveAuthoritativeBase(wire, 1000) != 0) {
    return Fail("initial authoritative base changed restore epoch");
  }
  if (!completionist::delivery_test::NoteKilled(
          "raven_642d0d164af0a5d4076e77933c549a5d") ||
      completionist::delivery_test::MergeCurrentEpochKills(wire).killed_count !=
          28) {
    return Fail("pre-fresh session kill setup differs");
  }
  if (completionist::delivery_test::ObserveAuthoritativeBase(wire, 1100) != 0) {
    return Fail("unchanged authoritative base inferred a boundary");
  }

  completionist::NativeRavenSnapshot fresh = wire;
  fresh.killed.fill(false);
  fresh.killed_count = 0;
  fresh.alive_count = 53;
  fresh.explicit_count = 0;
  fresh.absence_default_false_count = 53;

  const std::uint64_t inferred_fresh_epoch =
      completionist::delivery_test::ObserveAuthoritativeBase(fresh, 5000);
  if (inferred_fresh_epoch != 1 ||
      completionist::delivery_test::CurrentRestoreEpoch() != 1) {
    return Fail("authoritative revival did not infer fresh restore epoch");
  }
  if (completionist::delivery_test::MergeCurrentEpochKills(fresh).killed_count !=
      0) {
    return Fail("old session kill leaked into inferred fresh epoch");
  }
  if (completionist::delivery_test::ObserveAuthoritativeBase(fresh, 5100) != 1) {
    return Fail("stable fresh authority advanced restore epoch twice");
  }
  if (completionist::delivery_test::NoteRestoreBoundary(5200) != 1) {
    return Fail("post-inference duplicate Raven restore did not coalesce");
  }

  // If a gameplay restore already advanced the epoch, a later raw revival is
  // the expected saved-state change for that boundary and must not double-step.
  completionist::delivery_test::ResetSessionAuthority();
  if (completionist::delivery_test::ObserveAuthoritativeBase(wire, 1000) != 0 ||
      completionist::delivery_test::NoteRestoreBoundary(5000) != 1 ||
      completionist::delivery_test::ObserveAuthoritativeBase(fresh, 5100) != 1) {
    return Fail("explicit restore plus authoritative revival double-advanced");
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

  // Field regression 2026-09-22: a complete post-boundary snapshot was
  // captured, then a later WAD unload made one Raven undecodable. The proven
  // boundary image must remain usable for the same restore epoch only.
  completionist::delivery_test::ResetSessionAuthority();
  if (completionist::delivery_test::NoteRestoreBoundary(5000) != 1) {
    return Fail("boundary-cache setup did not advance to epoch 1");
  }
  completionist::delivery_test::CacheBoundarySnapshot(wire, 1);
  completionist::NativeRavenSnapshot cached_boundary;
  if (!completionist::delivery_test::ReadBoundarySnapshot(
          1, &cached_boundary) ||
      cached_boundary.generation != wire.generation ||
      cached_boundary.killed != wire.killed ||
      cached_boundary.killed_count != 27) {
    return Fail("same-epoch proven boundary snapshot was not retained");
  }
  if (!completionist::delivery_test::NoteKilled(
          "raven_642d0d164af0a5d4076e77933c549a5d")) {
    return Fail("boundary-cache session kill note rejected");
  }
  completionist::NativeRavenSnapshot cached_raw;
  if (!completionist::delivery_test::ReadBoundarySnapshot(1, &cached_raw) ||
      cached_raw.killed_count != 27 ||
      completionist::delivery_test::MergeCurrentEpochKills(cached_raw)
              .killed_count != 28) {
    return Fail("boundary cache did not keep raw authority separate from overlay");
  }
  if (completionist::delivery_test::NoteRestoreBoundary(8000) != 2) {
    return Fail("later restore did not advance cached-boundary epoch");
  }
  if (completionist::delivery_test::ReadBoundarySnapshot(
          1, &cached_boundary) ||
      completionist::delivery_test::ReadBoundarySnapshot(
          2, &cached_boundary)) {
    return Fail("restore boundary did not invalidate proven snapshot cache");
  }
  completionist::delivery_test::CacheBoundarySnapshot(wire, 1);
  if (completionist::delivery_test::ReadBoundarySnapshot(
          1, &cached_boundary) ||
      completionist::delivery_test::ReadBoundarySnapshot(
          2, &cached_boundary)) {
    return Fail("stale restore epoch was allowed to repopulate boundary cache");
  }
  completionist::delivery_test::CacheBoundarySnapshot(fresh, 2);
  if (!completionist::delivery_test::ReadBoundarySnapshot(
          2, &cached_boundary) ||
      cached_boundary.killed_count != 0) {
    return Fail("current restore epoch could not establish new boundary cache");
  }

  // The same invalidation is mandatory for a restore inferred from a
  // killed-to-alive authoritative transition, not only explicit checkpoint
  // notes.
  completionist::delivery_test::ResetSessionAuthority();
  if (completionist::delivery_test::ObserveAuthoritativeBase(wire, 1000) != 0) {
    return Fail("inferred-boundary cache setup changed epoch");
  }
  completionist::delivery_test::CacheBoundarySnapshot(wire, 0);
  if (!completionist::delivery_test::ReadBoundarySnapshot(
          0, &cached_boundary)) {
    return Fail("epoch-0 boundary cache setup failed");
  }
  if (completionist::delivery_test::ObserveAuthoritativeBase(fresh, 5000) != 1 ||
      completionist::delivery_test::ReadBoundarySnapshot(
          0, &cached_boundary) ||
      completionist::delivery_test::ReadBoundarySnapshot(
          1, &cached_boundary)) {
    return Fail("inferred restore did not invalidate proven snapshot cache");
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
               "collision_refused=true freshness_generation=true boundary_epoch_wire=true session_epoch_overlay=true inferred_restore_epoch=true boundary_snapshot_cache=true partial_snapshot_wire=true\n";
  return 0;
}
