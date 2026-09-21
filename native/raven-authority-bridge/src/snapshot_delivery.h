#pragma once

#include <cstdint>
#include <string>

#include "authority_runtime.h"

namespace completionist {

inline constexpr std::uint16_t kSnapshotDeliveryPort = 43753;

std::string BuildRavenSnapshotWireResponse(
    const NativeRavenSnapshot& snapshot);

using SnapshotReader = bool (*)(NativeRavenSnapshot* snapshot);

// Start one read-only loopback endpoint. Repeated calls are idempotent. A port
// collision or any listener failure is final and fail-closed for this process.
bool StartSnapshotDeliveryServer(SnapshotReader reader);

namespace delivery_test {

inline constexpr std::uintptr_t kInvalidListener =
    static_cast<std::uintptr_t>(~std::uintptr_t{0});

std::uintptr_t OpenLoopbackListener(std::uint16_t port,
                                    std::uint16_t* bound_port,
                                    int* error);
void CloseLoopbackListener(std::uintptr_t listener);

}  // namespace delivery_test
}  // namespace completionist
