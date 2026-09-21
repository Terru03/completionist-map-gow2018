#include "authority_runtime.h"

namespace completionist {

void SnapshotStore::Publish(const NativeRavenSnapshot& snapshot) {
  std::lock_guard lock(mutex_);
  snapshot_ = snapshot;
  snapshot_.generation = next_generation_++;
  ready_ = true;
}

bool SnapshotStore::Read(NativeRavenSnapshot* snapshot) const {
  if (snapshot == nullptr) return false;
  std::lock_guard lock(mutex_);
  if (!ready_) return false;
  *snapshot = snapshot_;
  return true;
}

}  // namespace completionist
