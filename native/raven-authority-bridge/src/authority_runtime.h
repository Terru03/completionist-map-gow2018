#pragma once

#include <windows.h>

#include <array>
#include <cstdint>
#include <mutex>

namespace completionist {

struct NativeRavenSnapshot {
  std::array<bool, 53> killed{};
  std::uint64_t generation = 0;
  std::uint64_t captured_tick_ms = 0;
  std::uint32_t alive_count = 0;
  std::uint32_t killed_count = 0;
  std::uint32_t explicit_count = 0;
  std::uint32_t absence_default_false_count = 0;
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

void RunAuthorityWorker();
void SetProxyForwardReady(bool ready);
bool ReadPublishedSnapshot(NativeRavenSnapshot* snapshot);

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
