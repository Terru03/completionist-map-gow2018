#pragma once

#include <windows.h>

#include <array>
#include <cstdint>
#include <mutex>

namespace completionist {

struct NativeRavenSnapshot {
  std::array<bool, 53> killed{};
  std::array<bool, 53> known{};
  std::array<bool, 53> explicit_state{};
  std::array<bool, 53> absence_default_state{};
  std::uint64_t generation = 0;
  std::uint64_t captured_tick_ms = 0;
  std::uint32_t alive_count = 0;
  std::uint32_t killed_count = 0;
  std::uint32_t explicit_count = 0;
  std::uint32_t absence_default_false_count = 0;
  std::uint32_t unknown_count = 53;
  bool partial_usable = false;
};

class SnapshotStore {
 public:
  void Publish(const NativeRavenSnapshot& snapshot);
  bool Read(NativeRavenSnapshot* snapshot) const;

 private:
  mutable std::mutex mutex_;
  NativeRavenSnapshot snapshot_{};
  bool ready_ = false;
  std::uint64_t next_generation_ = 1;
};

// Prevent a transient startup image where all 53 Ravens appear default-alive
// from becoming authority before the staged checkpoint table has settled.
class SnapshotPublicationGate {
 public:
  bool Observe(const NativeRavenSnapshot& snapshot, std::uint64_t now_ms) {
    bool all_false = snapshot.alive_count == 53 &&
                     snapshot.killed_count == 0 &&
                     snapshot.explicit_count == 0 &&
                     snapshot.absence_default_false_count == 53;
    if (all_false) {
      for (const bool killed : snapshot.killed) {
        if (killed) {
          all_false = false;
          break;
        }
      }
    }

    if (!all_false) {
      zero_pending_ = false;
      zero_confirmed_ = false;
      zero_first_tick_ms_ = 0;
      return true;
    }

    if (zero_confirmed_) return true;
    if (!zero_pending_) {
      zero_pending_ = true;
      zero_first_tick_ms_ = now_ms;
      return false;
    }
    if (now_ms < zero_first_tick_ms_ ||
        now_ms - zero_first_tick_ms_ < 750) {
      return false;
    }
    zero_confirmed_ = true;
    return true;
  }

  void Reject() {
    zero_pending_ = false;
    zero_confirmed_ = false;
    zero_first_tick_ms_ = 0;
  }

 private:
  bool zero_pending_ = false;
  bool zero_confirmed_ = false;
  std::uint64_t zero_first_tick_ms_ = 0;
};

void RunAuthorityWorker();
void SetProxyForwardReady(bool ready);
bool ReadPublishedSnapshot(NativeRavenSnapshot* snapshot);
bool CaptureFreshSnapshot(NativeRavenSnapshot* snapshot);

}  // namespace completionist

extern "C" {

struct CompletionistRavenStateV1 {
  char catalogue_id[40];
  std::uint8_t killed;
  std::uint8_t reserved[7];
};

struct CompletionistRavenSnapshotV1 {
  std::uint32_t size;
  std::uint32_t schema;
  std::uint64_t generation;
  std::uint64_t captured_tick_ms;
  std::uint32_t state_count;
  std::uint32_t alive_count;
  std::uint32_t killed_count;
  std::uint32_t unknown_count;
  std::uint32_t explicit_count;
  std::uint32_t absence_default_false_count;
  CompletionistRavenStateV1 states[53];
};

BOOL WINAPI CompletionistMapGetRavenSnapshotV1(
    CompletionistRavenSnapshotV1* output);

}
