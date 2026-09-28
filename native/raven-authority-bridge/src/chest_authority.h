#pragma once

#include "authority_decoder.h"
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace completionist {

enum class ChestState : std::uint8_t {
  Unknown = 0, Enabled = 1, Disabled = 2, Locked = 3, Opened = 4
};

using ChestIdentity = NumericStateIdentity;

struct DecodedChestSnapshot {
  bool accepted = false;
  std::vector<ChestState> states;
  std::size_t opened_count = 0;
  std::size_t remaining_count = 0;
  std::size_t unknown_count = 0;
  std::string reason;
};

DecodedChestSnapshot DecodeStandardChestSnapshot(
    std::span<const StagedRecordInput> records,
    std::span<const ChestIdentity> identities);

// Own state only. No game, save, or progression writes.
class ChestSessionAuthority {
 public:
  explicit ChestSessionAuthority(std::size_t count);
  bool BeginBoundary(std::uint64_t epoch);
  bool Apply(const DecodedChestSnapshot& snapshot, std::uint64_t epoch,
             std::uint64_t generation);
  bool NoteOpened(std::size_t index, std::uint64_t epoch);
  std::span<const ChestState> States() const { return states_; }

 private:
  std::vector<ChestState> states_;
  std::vector<bool> opened_;
  std::uint64_t epoch_ = 0;
  std::uint64_t generation_ = 0;
};

}  // namespace completionist
