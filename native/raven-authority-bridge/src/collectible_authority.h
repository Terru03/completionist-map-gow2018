#pragma once
#include "authority_decoder.h"

namespace completionist {
std::string CollectibleSnapshotResponse(std::span<const StagedRecordInput> records,
    std::uint64_t nonce, std::uint64_t restore_epoch, std::uint64_t generation);
}
