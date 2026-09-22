#include "authority_runtime.h"

#include <windows.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <span>
#include <string>
#include <vector>
#include <mutex>

#include "authority_decoder.h"
#include "hash.h"
#include "platform.h"
#include "raven_catalogue.generated.h"
#include "snapshot_delivery.h"

namespace completionist {
namespace {

constexpr std::uintptr_t kPayloadSizeRva = 0x22C6938;
constexpr std::uintptr_t kPayloadBaseRva = 0x22C6940;
constexpr std::uintptr_t kRecordCountRva = 0x22C696C;
constexpr std::uintptr_t kRecordBaseRva = 0x22C7170;
constexpr std::uintptr_t kTransientLoadSlotRva = 0x1078F4C;
constexpr std::size_t kRecordStride = 0xA8;
constexpr std::size_t kMaxRecords = 4096;
constexpr std::size_t kMaxPoolSize = 0x140000;
constexpr std::size_t kMaxCarrierBytes = 0x4800;

struct StagedHeader {
  std::uint32_t pool_size = 0;
  std::uintptr_t pool_base = 0;
  std::uint32_t record_count = 0;

  auto operator<=>(const StagedHeader&) const = default;
};

SnapshotStore g_snapshot_store;
SnapshotPublicationGate g_publication_gate;
std::atomic<bool> g_proxy_forward_ready{false};
std::atomic<std::uintptr_t> g_module_base{0};
std::mutex g_capture_mutex;

bool SafeCopy(const void* source, void* destination, std::size_t length) {
  if (source == nullptr || destination == nullptr || length == 0) return false;
  __try {
    std::memcpy(destination, source, length);
    return true;
  } __except (EXCEPTION_EXECUTE_HANDLER) {
    return false;
  }
}

template <typename T>
bool ReadValue(std::uintptr_t address, T* value) {
  return SafeCopy(reinterpret_cast<const void*>(address), value, sizeof(T));
}

template <typename T>
bool ReadLe(std::span<const std::uint8_t> bytes, std::size_t offset,
            T* value) {
  if (value == nullptr || offset > bytes.size() ||
      sizeof(T) > bytes.size() - offset) {
    return false;
  }
  T result = 0;
  for (std::size_t index = 0; index < sizeof(T); ++index) {
    result |= static_cast<T>(bytes[offset + index]) << (index * 8);
  }
  *value = result;
  return true;
}

bool ReadStagedHeader(std::uintptr_t module_base, StagedHeader* header,
                      std::string* reason) {
  StagedHeader value;
  if (!ReadValue(module_base + kPayloadSizeRva, &value.pool_size) ||
      !ReadValue(module_base + kPayloadBaseRva, &value.pool_base) ||
      !ReadValue(module_base + kRecordCountRva, &value.record_count)) {
    *reason = "staged_header_unreadable";
    return false;
  }
  if (value.record_count == 0 || value.record_count > kMaxRecords) {
    *reason = "staged_record_count_invalid";
    return false;
  }
  if (value.pool_size == 0 || value.pool_size > kMaxPoolSize) {
    *reason = "staged_pool_size_invalid";
    return false;
  }
  if (value.pool_base < 0x10000 ||
      value.pool_base >= UINT64_C(0x0000800000000000) ||
      value.pool_size > UINT64_C(0x0000800000000000) - value.pool_base) {
    *reason = "staged_pool_pointer_invalid";
    return false;
  }
  *header = value;
  return true;
}

std::string PrintableName(std::span<const std::uint8_t> bytes) {
  std::string output;
  for (const std::uint8_t value : bytes) {
    if (value == 0) break;
    if (value < 32 || value >= 127) return {};
    output.push_back(static_cast<char>(value));
  }
  return output;
}

bool CaptureRecords(std::uintptr_t module_base,
                    std::vector<StagedRecordInput>* records,
                    std::string* reason) {
  StagedHeader before;
  if (!ReadStagedHeader(module_base, &before, reason)) return false;
  const std::size_t table_size =
      static_cast<std::size_t>(before.record_count) * kRecordStride;
  std::vector<std::uint8_t> table(table_size);
  std::vector<std::uint8_t> pool(before.pool_size);
  std::vector<std::uint8_t> table_verify(table_size);
  std::vector<std::uint8_t> pool_verify(before.pool_size);
  if (!SafeCopy(reinterpret_cast<const void*>(module_base + kRecordBaseRva),
                table.data(), table.size()) ||
      !SafeCopy(reinterpret_cast<const void*>(before.pool_base), pool.data(),
                pool.size())) {
    *reason = "staged_snapshot_unreadable";
    return false;
  }
  StagedHeader middle;
  if (!ReadStagedHeader(module_base, &middle, reason) || middle != before ||
      !SafeCopy(reinterpret_cast<const void*>(module_base + kRecordBaseRva),
                table_verify.data(), table_verify.size()) ||
      !SafeCopy(reinterpret_cast<const void*>(before.pool_base),
                pool_verify.data(), pool_verify.size())) {
    *reason = "staged_snapshot_changed";
    return false;
  }
  StagedHeader after;
  if (!ReadStagedHeader(module_base, &after, reason) || after != before ||
      table != table_verify || pool != pool_verify) {
    *reason = "staged_snapshot_changed";
    return false;
  }

  records->clear();
  records->reserve(before.record_count);
  for (std::size_t index = 0; index < before.record_count; ++index) {
    const std::span<const std::uint8_t> raw(table.data() + index * kRecordStride,
                                           kRecordStride);
    std::uint64_t payload_address = 0;
    std::uint64_t cursor = 0;
    std::uint32_t payload_length = 0;
    std::uint32_t lua_length = 0;
    std::uint16_t slot_bits = 0;
    if (!ReadLe(raw, 0x30, &payload_address) ||
        !ReadLe(raw, 0x38, &cursor) ||
        !ReadLe(raw, 0x40, &payload_length) ||
        !ReadLe(raw, 0x60, &lua_length) ||
        !ReadLe(raw, 0x28, &slot_bits)) {
      *reason = "staged_record_fields_invalid";
      return false;
    }
    const std::int16_t slot = static_cast<std::int16_t>(slot_bits);
    if (slot < -1 || slot >= 64 || lua_length > kMaxCarrierBytes) {
      *reason = "staged_record_bounds_invalid";
      return false;
    }
    StagedRecordInput record;
    record.name = PrintableName(raw.subspan(0x84, 0x24));
    record.expected_lua_length = lua_length;
    if (payload_length != 0) {
      if (payload_length > 0x10001 || payload_address < before.pool_base ||
          payload_address - before.pool_base > pool.size() ||
          payload_length > pool.size() -
                               static_cast<std::size_t>(payload_address -
                                                        before.pool_base) ||
          cursor < payload_address ||
          cursor > payload_address + payload_length) {
        *reason = "staged_record_payload_outside_pool";
        return false;
      }
      const std::size_t offset =
          static_cast<std::size_t>(payload_address - before.pool_base);
      record.envelope.assign(pool.begin() + offset,
                             pool.begin() + offset + payload_length);
    }
    records->push_back(std::move(record));
  }
  return true;
}

bool SameState(const NativeRavenSnapshot& left,
               const NativeRavenSnapshot& right) {
  return left.killed == right.killed &&
         left.alive_count == right.alive_count &&
         left.killed_count == right.killed_count &&
         left.explicit_count == right.explicit_count &&
         left.absence_default_false_count ==
             right.absence_default_false_count;
}

bool CaptureAcceptedSnapshot(std::uintptr_t module_base,
                             NativeRavenSnapshot* output,
                             std::string* reason) {
  if (output == nullptr || reason == nullptr || module_base == 0) return false;
  std::lock_guard<std::mutex> lock(g_capture_mutex);
  *output = NativeRavenSnapshot{};

  std::vector<StagedRecordInput> records;
  if (!CaptureRecords(module_base, &records, reason)) {
    g_publication_gate.Reject();
    return false;
  }

  const DecodedRavenSnapshot decoded = DecodeRavenSnapshot(records);
  if (!decoded.accepted) {
    g_publication_gate.Reject();

    const bool safe_partial =
        decoded.unknown_count > 0 &&
        decoded.unknown_count < kRavenCatalogue.size() &&
        decoded.reason.rfind("present_wad_without_exact_state:", 0) == 0;
    if (safe_partial) {
      output->killed = decoded.killed;
      output->known = decoded.known;
      output->explicit_state = decoded.explicit_state;
      for (std::size_t index = 0; index < kRavenCatalogue.size(); ++index) {
        output->absence_default_state[index] =
            decoded.known[index] && !decoded.explicit_state[index];
      }
      output->captured_tick_ms = GetTickCount64();
      output->alive_count = decoded.alive_count;
      output->killed_count = decoded.killed_count;
      output->explicit_count = decoded.explicit_count;
      output->absence_default_false_count =
          decoded.absence_default_false_count;
      output->unknown_count = decoded.unknown_count;
      output->partial_usable = true;
    }

    std::string diagnostic = decoded.reason +
        " explicit=" + std::to_string(decoded.explicit_count) +
        " absentWadFalse=" +
        std::to_string(decoded.absence_default_false_count) +
        " unknown=" + std::to_string(decoded.unknown_count) +
        " knownKilled=" + std::to_string(decoded.killed_count) +
        " stagedRecords=" + std::to_string(records.size());

    std::int32_t load_slot = INT32_MIN;
    if (ReadValue(module_base + kTransientLoadSlotRva, &load_slot)) {
      diagnostic += " transientLoadSlot=" + std::to_string(load_slot);
    }

    std::string unknown_ids;
    std::string explicit_killed_ids;
    std::string explicit_alive_ids;
    std::string absent_ids;
    for (std::size_t index = 0; index < kRavenCatalogue.size(); ++index) {
      auto append_id = [&](std::string* target) {
        if (!target->empty()) target->push_back(',');
        target->append(kRavenCatalogue[index].catalogue_id);
      };
      if (!decoded.known[index]) {
        append_id(&unknown_ids);
      } else if (decoded.explicit_state[index]) {
        if (decoded.killed[index]) {
          append_id(&explicit_killed_ids);
        } else {
          append_id(&explicit_alive_ids);
        }
      } else {
        append_id(&absent_ids);
      }
    }
    diagnostic += " unknownIds=" +
        (unknown_ids.empty() ? std::string("-") : unknown_ids);
    diagnostic += " explicitKilledIds=" +
        (explicit_killed_ids.empty() ? std::string("-") : explicit_killed_ids);
    diagnostic += " explicitAliveIds=" +
        (explicit_alive_ids.empty() ? std::string("-") : explicit_alive_ids);
    diagnostic += " absentWadIds=" +
        (absent_ids.empty() ? std::string("-") : absent_ids);

    *reason = std::move(diagnostic);
    return false;
  }

  NativeRavenSnapshot snapshot;
  snapshot.killed = decoded.killed;
  snapshot.known.fill(true);
  snapshot.explicit_state = decoded.explicit_state;
  for (std::size_t index = 0; index < kRavenCatalogue.size(); ++index) {
    snapshot.absence_default_state[index] = !decoded.explicit_state[index];
  }
  snapshot.captured_tick_ms = GetTickCount64();
  snapshot.alive_count = decoded.alive_count;
  snapshot.killed_count = decoded.killed_count;
  snapshot.explicit_count = decoded.explicit_count;
  snapshot.absence_default_false_count =
      decoded.absence_default_false_count;
  snapshot.unknown_count = 0;
  snapshot.partial_usable = false;

  const bool stable_zero_candidate =
      snapshot.killed_count == 0 &&
      snapshot.alive_count == kRavenCatalogue.size() &&
      snapshot.explicit_count == 0 &&
      snapshot.absence_default_false_count == kRavenCatalogue.size();

  // A nonzero image containing WAD-absence defaults is not exact authority.
  // Those false values only mean the WAD was not staged. Preserve the image
  // as partial evidence so Lua can reconcile it against live RegionSummary.
  if (snapshot.absence_default_false_count > 0 && !stable_zero_candidate) {
    snapshot.partial_usable = true;
    *output = snapshot;
    g_publication_gate.Reject();
    *reason = "absence_default_requires_region_summary";
    return false;
  }

  if (!g_publication_gate.Observe(snapshot, snapshot.captured_tick_ms)) {
    *reason = "all_false_authority_unconfirmed";
    return false;
  }

  g_snapshot_store.Publish(snapshot);
  if (!g_snapshot_store.Read(output)) {
    *reason = "snapshot_store_unavailable";
    return false;
  }
  reason->clear();
  return true;
}

}  // namespace

void RunAuthorityWorker() {
  AppendBridgeLog(
      "RAVEN_NATIVE_BRIDGE_PROXY_LOADED target=dxgi.dll real=system32 "
      "save_writes=false progression_writes=false");
  AppendBridgeLog(
      std::string("RAVEN_NATIVE_BRIDGE_DXGI_FORWARDED exports=20 success=") +
      (g_proxy_forward_ready.load() ? "true" : "false"));
  std::wstring executable;
  DWORD path_error = ERROR_SUCCESS;
  if (!BuildModulePath(&executable, &path_error)) {
    AppendBridgeLog("RAVEN_NATIVE_BRIDGE_REJECTED reason=exe_path_failed:" +
                    std::to_string(path_error));
    return;
  }
  Sha256 digest{};
  std::string hash_reason;
  if (!Sha256File(executable, &digest, &hash_reason)) {
    AppendBridgeLog("RAVEN_NATIVE_BRIDGE_REJECTED reason=" + hash_reason);
    return;
  }
  const std::string hash = Sha256Hex(digest);
  if (!IsSupportedExecutableHash(digest)) {
    AppendBridgeLog("RAVEN_NATIVE_BRIDGE_REJECTED reason=unsupported_exe sha256=" +
                    hash);
    return;
  }
  AppendBridgeLog("RAVEN_NATIVE_BRIDGE_EXE_ACCEPTED sha256=" + hash);
  const std::uintptr_t module_base = reinterpret_cast<std::uintptr_t>(
      GetModuleHandleW(nullptr));
  if (module_base == 0) {
    AppendBridgeLog("RAVEN_NATIVE_BRIDGE_REJECTED reason=module_base_missing");
    return;
  }
  g_module_base.store(module_base);
  StartSnapshotDeliveryServer(ReadPublishedSnapshot, CaptureFreshSnapshot);
  std::string last_reason;
  NativeRavenSnapshot last_snapshot;
  bool have_last_snapshot = false;
  for (;;) {
    std::string reason;
    NativeRavenSnapshot snapshot;
    if (!CaptureAcceptedSnapshot(module_base, &snapshot, &reason)) {
      if (reason != last_reason) {
        AppendBridgeLog("RAVEN_NATIVE_BRIDGE_WAIT reason=" + reason);
        last_reason = reason;
      }
      Sleep(1000);
      continue;
    }

    const bool state_changed =
        !have_last_snapshot || !SameState(snapshot, last_snapshot);
    if (state_changed) {
      AppendBridgeLog(
          "RAVEN_NATIVE_BRIDGE_SNAPSHOT_ACCEPTED generation=" +
          std::to_string(snapshot.generation) + " count=53 unknown=0 alive=" +
          std::to_string(snapshot.alive_count) + " killed=" +
          std::to_string(snapshot.killed_count) + " explicit=" +
          std::to_string(snapshot.explicit_count) + " absentWadFalse=" +
          std::to_string(snapshot.absence_default_false_count));
      AppendBridgeLog(
          "RAVEN_NATIVE_BRIDGE_DELIVERY_PENDING mechanism=native_snapshot_api "
          "save_writes=false progression_writes=false");
    }
    last_snapshot = snapshot;
    have_last_snapshot = true;
    last_reason.clear();
    Sleep(1000);
  }
}

void SetProxyForwardReady(bool ready) {
  g_proxy_forward_ready.store(ready);
}

bool ReadPublishedSnapshot(NativeRavenSnapshot* snapshot) {
  return g_snapshot_store.Read(snapshot);
}

bool CaptureFreshSnapshot(NativeRavenSnapshot* snapshot) {
  const std::uintptr_t module_base = g_module_base.load();
  if (module_base == 0 || snapshot == nullptr) return false;

  std::string reason;
  if (!CaptureAcceptedSnapshot(module_base, snapshot, &reason)) {
    AppendBridgeLog(
        "RAVEN_NATIVE_BRIDGE_BOUNDARY_CAPTURE_REJECTED reason=" + reason +
        " save_writes=false progression_writes=false");
    return false;
  }

  AppendBridgeLog(
      "RAVEN_NATIVE_BRIDGE_BOUNDARY_CAPTURED generation=" +
      std::to_string(snapshot->generation) + " count=53 alive=" +
      std::to_string(snapshot->alive_count) + " killed=" +
      std::to_string(snapshot->killed_count) +
      " save_writes=false progression_writes=false");
  return true;
}

}  // namespace completionist

extern "C" BOOL WINAPI CompletionistMapGetRavenSnapshotV1(
    CompletionistRavenSnapshotV1* output) {
  if (output == nullptr || output->size != sizeof(*output)) return FALSE;
  completionist::NativeRavenSnapshot snapshot;
  if (!completionist::ReadPublishedSnapshot(&snapshot)) return FALSE;
  CompletionistRavenSnapshotV1 result{};
  result.size = sizeof(result);
  result.schema = 1;
  result.generation = snapshot.generation;
  result.captured_tick_ms = snapshot.captured_tick_ms;
  result.state_count = 53;
  result.alive_count = snapshot.alive_count;
  result.killed_count = snapshot.killed_count;
  result.unknown_count = 0;
  result.explicit_count = snapshot.explicit_count;
  result.absence_default_false_count =
      snapshot.absence_default_false_count;
  for (std::size_t index = 0; index < 53; ++index) {
    const std::string_view id = completionist::kRavenCatalogue[index].catalogue_id;
    const std::size_t copy_length =
        (std::min)(id.size(), sizeof(result.states[index].catalogue_id) - 1);
    std::memcpy(result.states[index].catalogue_id, id.data(), copy_length);
    result.states[index].killed = snapshot.killed[index] ? 1 : 0;
  }
  *output = result;
  return TRUE;
}
