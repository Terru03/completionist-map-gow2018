#pragma once

#include <cstdint>
#include <string>
#include <string_view>

#include "authority_runtime.h"

namespace completionist {

inline constexpr std::uint16_t kSnapshotDeliveryPort = 43753;

std::string BuildRavenSnapshotWireResponse(
    const NativeRavenSnapshot& snapshot, std::uint64_t restore_epoch);
std::string BuildRavenBoundarySnapshotWireResponse(
    const NativeRavenSnapshot& snapshot, std::uint64_t boundary_epoch);
std::string BuildRavenPartialSnapshotWireResponse(
    const NativeRavenSnapshot& snapshot, std::uint64_t restore_epoch);
std::string BuildRavenPartialBoundarySnapshotWireResponse(
    const NativeRavenSnapshot& snapshot, std::uint64_t boundary_epoch);

using SnapshotReader = bool (*)(NativeRavenSnapshot* snapshot);
using SnapshotCapturer = bool (*)(NativeRavenSnapshot* snapshot);

// Start one read-only loopback endpoint. Repeated calls are idempotent. A port
// collision or any listener failure is final and fail-closed for this process.
bool StartSnapshotDeliveryServer(SnapshotReader reader,
                                 SnapshotCapturer capturer);

namespace delivery_test {

inline constexpr std::uintptr_t kInvalidListener =
    static_cast<std::uintptr_t>(~std::uintptr_t{0});

std::uintptr_t OpenLoopbackListener(std::uint16_t port,
                                    std::uint16_t* bound_port,
                                    int* error);
void CloseLoopbackListener(std::uintptr_t listener);

// Deterministic session-authority helpers used by native tests. These mutate
// only the bridge's own process-local overlay, never game/save/progression
// state.
void ResetSessionAuthority();
std::uint64_t NoteRestoreBoundary(std::uint64_t now_ms);
bool NoteKilled(std::string_view catalogue_id);
std::uint64_t CurrentRestoreEpoch();
std::uint64_t ObserveAuthoritativeBase(
    const NativeRavenSnapshot& snapshot, std::uint64_t now_ms);
NativeRavenSnapshot MergeCurrentEpochKills(
    const NativeRavenSnapshot& snapshot);
void CacheBoundarySnapshot(
    const NativeRavenSnapshot& snapshot, std::uint64_t boundary_epoch);
bool ReadBoundarySnapshot(
    std::uint64_t boundary_epoch, NativeRavenSnapshot* snapshot);

}  // namespace delivery_test
}  // namespace completionist
