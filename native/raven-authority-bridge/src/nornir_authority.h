#pragma once
#include "chest_authority.h"

namespace completionist {
DecodedChestSnapshot DecodeNornirSnapshot(std::span<const StagedRecordInput> records);
std::string NornirSnapshotResponse(const DecodedChestSnapshot& snapshot,
                                  std::uint64_t nonce, std::uint64_t restore_epoch);
}
