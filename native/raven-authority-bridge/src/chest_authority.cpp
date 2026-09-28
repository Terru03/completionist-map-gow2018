#include "chest_authority.h"
#include <algorithm>

namespace completionist {

ChestSessionAuthority::ChestSessionAuthority(std::size_t count)
    : states_(count, ChestState::Unknown), opened_(count, false) {}

bool ChestSessionAuthority::BeginBoundary(std::uint64_t epoch) {
  if (epoch == 0 || epoch <= epoch_) return false;
  epoch_ = epoch;
  generation_ = 0;
  std::fill(states_.begin(), states_.end(), ChestState::Unknown);
  std::fill(opened_.begin(), opened_.end(), false);
  return true;
}

bool ChestSessionAuthority::Apply(const DecodedChestSnapshot& snapshot,
                                 std::uint64_t epoch,
                                 std::uint64_t generation) {
  if (!snapshot.accepted || epoch_ == 0 || epoch != epoch_ ||
      generation <= generation_ || snapshot.states.size() != states_.size())
    return false;
  std::size_t opened = 0, remaining = 0, unknown = 0;
  for (const auto state : snapshot.states) {
    switch (state) {
      case ChestState::Unknown: ++unknown; break;
      case ChestState::Opened: ++opened; break;
      case ChestState::Enabled:
      case ChestState::Disabled:
      case ChestState::Locked: ++remaining; break;
      default: return false;
    }
  }
  if (opened != snapshot.opened_count || remaining != snapshot.remaining_count ||
      unknown != snapshot.unknown_count) return false;
  for (std::size_t i = 0; i < states_.size(); ++i) {
    opened_[i] = opened_[i] || snapshot.states[i] == ChestState::Opened;
    states_[i] = opened_[i] ? ChestState::Opened : snapshot.states[i];
  }
  generation_ = generation;
  return true;
}

bool ChestSessionAuthority::NoteOpened(std::size_t index, std::uint64_t epoch) {
  if (epoch_ == 0 || epoch != epoch_ || index >= states_.size()) return false;
  opened_[index] = true;
  states_[index] = ChestState::Opened;
  return true;
}

}  // namespace completionist
