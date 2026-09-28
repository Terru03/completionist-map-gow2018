#include <winsock2.h>
#include <ws2tcpip.h>

#include "snapshot_delivery.h"

#include <process.h>

#include <array>
#include <atomic>
#include <cstdint>
#include <limits>
#include <mutex>
#include <memory>
#include <new>
#include <string>
#include <string_view>

#include "platform.h"
#include "raven_catalogue.generated.h"

namespace completionist {
namespace {

constexpr char kRequestV1[] = "GET RAVEN_SNAPSHOT_V1\n";
constexpr char kBoundaryPrefix[] =
    "CAPTURE RAVEN_SNAPSHOT_V2 boundaryEpoch=";
constexpr char kKillPrefix[] =
    "NOTE RAVEN_KILLED_V1 catalogueId=";
constexpr char kBoundaryNoteRequest[] =
    "NOTE RAVEN_BOUNDARY_V1 source=checkpoint\n";
constexpr std::uint64_t kBoundaryCoalesceMs = 1500;
constexpr int kClientTimeoutMs = 250;
constexpr std::size_t kMaxRequestBytes = 160;

enum class RequestKind {
  kInvalid = 0,
  kLatestV1 = 1,
  kBoundaryCaptureV2 = 2,
  kNoteKilledV1 = 3,
  kNoteBoundaryV1 = 4,
  kNornirCaptureV1 = 5,
  kCollectibleCaptureV1 = 6,
};

struct SnapshotRequest {
  RequestKind kind = RequestKind::kInvalid;
  std::uint64_t boundary_epoch = 0;
  std::string catalogue_id;
};

enum class ServerState : int {
  kNotStarted = 0,
  kStarting = 1,
  kRunning = 2,
  kRefused = 3,
};

INIT_ONCE g_winsock_once = INIT_ONCE_STATIC_INIT;
int g_winsock_error = WSASYSNOTREADY;
std::atomic<ServerState> g_server_state{ServerState::kNotStarted};
SnapshotReader g_snapshot_reader = nullptr;
SnapshotCapturer g_snapshot_capturer = nullptr;
NornirCapturer g_nornir_capturer = nullptr;
NornirCapturer g_collectible_capturer = nullptr;
std::atomic<bool> g_nornir_busy{false};

std::mutex g_session_mutex;
std::uint64_t g_restore_epoch = 0;
std::uint64_t g_last_boundary_note_ms = 0;
bool g_have_boundary_note = false;
std::array<std::uint64_t, 53> g_kill_epochs{};
std::array<bool, 53> g_kill_noted{};

bool g_have_authoritative_base = false;
std::array<bool, 53> g_last_authoritative_killed{};
std::uint64_t g_last_authoritative_epoch = 0;

bool g_have_boundary_snapshot = false;
std::uint64_t g_boundary_snapshot_epoch = 0;
NativeRavenSnapshot g_boundary_snapshot{};

void ClearBoundarySnapshotLocked() {
  g_have_boundary_snapshot = false;
  g_boundary_snapshot_epoch = 0;
  g_boundary_snapshot = NativeRavenSnapshot{};
}

struct BaseObservation {
  std::uint64_t restore_epoch = 0;
  bool inferred_boundary = false;
  std::uint32_t revived_count = 0;
};

std::size_t FindCatalogueIndex(std::string_view catalogue_id) {
  for (std::size_t index = 0; index < kRavenCatalogue.size(); ++index) {
    if (kRavenCatalogue[index].catalogue_id == catalogue_id) return index;
  }
  return kRavenCatalogue.size();
}

std::uint64_t NoteRestoreBoundaryInternal(std::uint64_t now_ms,
                                          bool* advanced) {
  std::lock_guard<std::mutex> lock(g_session_mutex);
  const bool is_new =
      !g_have_boundary_note || now_ms < g_last_boundary_note_ms ||
      now_ms - g_last_boundary_note_ms > kBoundaryCoalesceMs;
  if (is_new) {
    ++g_restore_epoch;
    ClearBoundarySnapshotLocked();
  }
  g_have_boundary_note = true;
  g_last_boundary_note_ms = now_ms;
  if (advanced != nullptr) *advanced = is_new;
  return g_restore_epoch;
}

bool NoteKilledInternal(std::string_view catalogue_id,
                        std::uint64_t* restore_epoch) {
  const std::size_t index = FindCatalogueIndex(catalogue_id);
  if (index >= kRavenCatalogue.size()) return false;
  std::lock_guard<std::mutex> lock(g_session_mutex);
  g_kill_noted[index] = true;
  g_kill_epochs[index] = g_restore_epoch;
  if (restore_epoch != nullptr) *restore_epoch = g_restore_epoch;
  return true;
}

std::uint64_t CurrentRestoreEpochInternal() {
  std::lock_guard<std::mutex> lock(g_session_mutex);
  return g_restore_epoch;
}

void CacheBoundarySnapshotInternal(
    const NativeRavenSnapshot& snapshot, std::uint64_t boundary_epoch) {
  std::lock_guard<std::mutex> lock(g_session_mutex);
  if (boundary_epoch != g_restore_epoch) return;
  g_boundary_snapshot = snapshot;
  g_boundary_snapshot_epoch = boundary_epoch;
  g_have_boundary_snapshot = true;
}

bool ReadBoundarySnapshotInternal(
    std::uint64_t boundary_epoch, NativeRavenSnapshot* snapshot) {
  if (snapshot == nullptr) return false;
  std::lock_guard<std::mutex> lock(g_session_mutex);
  if (!g_have_boundary_snapshot ||
      g_boundary_snapshot_epoch != boundary_epoch ||
      boundary_epoch != g_restore_epoch) {
    return false;
  }
  *snapshot = g_boundary_snapshot;
  return true;
}

BaseObservation ObserveAuthoritativeBaseInternal(
    const NativeRavenSnapshot& snapshot, std::uint64_t now_ms,
    bool boundary_capture) {
  std::lock_guard<std::mutex> lock(g_session_mutex);

  BaseObservation result;
  result.restore_epoch = g_restore_epoch;

  if (!g_have_authoritative_base) {
    g_have_authoritative_base = true;
    g_last_authoritative_killed = snapshot.killed;
    g_last_authoritative_epoch = g_restore_epoch;
    return result;
  }

  bool any_change = false;
  for (std::size_t index = 0; index < snapshot.killed.size(); ++index) {
    if (g_last_authoritative_killed[index] != snapshot.killed[index]) {
      any_change = true;
    }
    if (g_last_authoritative_killed[index] && !snapshot.killed[index]) {
      ++result.revived_count;
    }
  }

  // A V2 capture belongs to an already-established boundary. Likewise, if
  // gameplay already advanced the bridge epoch, the next changed raw base
  // consumes that existing boundary instead of creating another one.
  if (boundary_capture) {
    g_last_authoritative_killed = snapshot.killed;
    g_last_authoritative_epoch = g_restore_epoch;
    result.restore_epoch = g_restore_epoch;
    return result;
  }

  if (g_restore_epoch > g_last_authoritative_epoch) {
    if (any_change) {
      g_last_authoritative_killed = snapshot.killed;
      g_last_authoritative_epoch = g_restore_epoch;
    }
    result.restore_epoch = g_restore_epoch;
    return result;
  }

  // Within one save/playthrough Raven progression is monotonic: a raw
  // authoritative killed=true becoming killed=false cannot be caused by
  // normal gameplay. It is process-wide evidence that another checkpoint,
  // save, or a fresh game became authoritative even if no Raven instance
  // emitted OnRestoreCheckpoint.
  if (result.revived_count > 0) {
    ++g_restore_epoch;
    ClearBoundarySnapshotLocked();
    g_have_boundary_note = true;
    g_last_boundary_note_ms = now_ms;
    result.restore_epoch = g_restore_epoch;
    result.inferred_boundary = true;
  }

  g_last_authoritative_killed = snapshot.killed;
  g_last_authoritative_epoch = g_restore_epoch;
  result.restore_epoch = g_restore_epoch;
  return result;
}

NativeRavenSnapshot MergeCurrentEpochKillsInternal(
    const NativeRavenSnapshot& snapshot) {
  NativeRavenSnapshot merged = snapshot;
  if (!merged.partial_usable) {
    merged.known.fill(true);
    merged.unknown_count = 0;
  }
  {
    std::lock_guard<std::mutex> lock(g_session_mutex);
    for (std::size_t index = 0; index < merged.killed.size(); ++index) {
      if (g_kill_noted[index] && g_kill_epochs[index] == g_restore_epoch) {
        if (!merged.known[index]) {
          merged.known[index] = true;
          if (merged.unknown_count > 0) --merged.unknown_count;
        }
        merged.killed[index] = true;
        merged.absence_default_state[index] = false;
      }
    }
  }
  merged.killed_count = 0;
  merged.absence_default_false_count = 0;
  std::uint32_t known_count = 0;
  for (std::size_t index = 0; index < merged.killed.size(); ++index) {
    if (merged.absence_default_state[index]) {
      ++merged.absence_default_false_count;
    }
    if (!merged.known[index]) continue;
    ++known_count;
    if (merged.killed[index]) ++merged.killed_count;
  }
  merged.alive_count = known_count - merged.killed_count;
  return merged;
}

BOOL CALLBACK InitializeWinsock(PINIT_ONCE, PVOID, PVOID*) {
  WSADATA data{};
  g_winsock_error = WSAStartup(MAKEWORD(2, 2), &data);
  if (g_winsock_error == 0 &&
      (LOBYTE(data.wVersion) != 2 || HIBYTE(data.wVersion) != 2)) {
    WSACleanup();
    g_winsock_error = WSAVERNOTSUPPORTED;
  }
  return TRUE;
}

bool EnsureWinsock(int* error) {
  InitOnceExecuteOnce(&g_winsock_once, InitializeWinsock, nullptr, nullptr);
  if (error != nullptr) *error = g_winsock_error;
  return g_winsock_error == 0;
}

SOCKET OpenListener(std::uint16_t port, std::uint16_t* bound_port,
                    int* error) {
  if (!EnsureWinsock(error)) return INVALID_SOCKET;
  SOCKET listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (listener == INVALID_SOCKET) {
    if (error != nullptr) *error = WSAGetLastError();
    return INVALID_SOCKET;
  }
  const BOOL exclusive = TRUE;
  if (setsockopt(listener, SOL_SOCKET, SO_EXCLUSIVEADDRUSE,
                 reinterpret_cast<const char*>(&exclusive),
                 sizeof(exclusive)) == SOCKET_ERROR) {
    if (error != nullptr) *error = WSAGetLastError();
    closesocket(listener);
    return INVALID_SOCKET;
  }
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  address.sin_port = htons(port);
  if (bind(listener, reinterpret_cast<const sockaddr*>(&address),
           sizeof(address)) == SOCKET_ERROR || listen(listener, 4) == SOCKET_ERROR) {
    if (error != nullptr) *error = WSAGetLastError();
    closesocket(listener);
    return INVALID_SOCKET;
  }
  if (bound_port != nullptr) {
    int size = sizeof(address);
    if (getsockname(listener, reinterpret_cast<sockaddr*>(&address), &size) ==
        SOCKET_ERROR) {
      if (error != nullptr) *error = WSAGetLastError();
      closesocket(listener);
      return INVALID_SOCKET;
    }
    *bound_port = ntohs(address.sin_port);
  }
  if (error != nullptr) *error = 0;
  return listener;
}

bool ParseBoundaryEpoch(std::string_view digits, std::uint64_t* value) {
  if (value == nullptr || digits.empty()) return false;
  std::uint64_t result = 0;
  for (const char ch : digits) {
    if (ch < '0' || ch > '9') return false;
    const std::uint64_t digit = static_cast<std::uint64_t>(ch - '0');
    if (result > (std::numeric_limits<std::uint64_t>::max() - digit) / 10) {
      return false;
    }
    result = result * 10 + digit;
  }
  if (result == 0) return false;
  *value = result;
  return true;
}

SnapshotRequest ReceiveRequest(SOCKET client) {
  std::array<char, kMaxRequestBytes> request{};
  std::size_t length = 0;
  while (length < request.size()) {
    const int received = recv(client, request.data() + length,
                              static_cast<int>(request.size() - length), 0);
    if (received <= 0) return {};
    length += static_cast<std::size_t>(received);
    if (request[length - 1] == '\n') break;
  }
  if (length == 0 || request[length - 1] != '\n') return {};

  const std::string_view text(request.data(), length);
  constexpr std::string_view collectible_prefix = "CAPTURE COLLECTIBLE_SNAPSHOT_V1 nonce=";
  if (text.starts_with(collectible_prefix)) {
    SnapshotRequest parsed;
    if (!ParseBoundaryEpoch(text.substr(collectible_prefix.size(), text.size() - collectible_prefix.size() - 1),
                            &parsed.boundary_epoch)) return {};
    parsed.kind = RequestKind::kCollectibleCaptureV1;
    return parsed;
  }
  constexpr std::string_view nornir_prefix = "CAPTURE NORNIR_SNAPSHOT_V1 nonce=";
  if (text.starts_with(nornir_prefix)) {
    SnapshotRequest parsed;
    if (!ParseBoundaryEpoch(text.substr(nornir_prefix.size(), text.size() - nornir_prefix.size() - 1),
                            &parsed.boundary_epoch)) return {};
    parsed.kind = RequestKind::kNornirCaptureV1;
    return parsed;
  }
  if (text == kRequestV1) {
    SnapshotRequest parsed;
    parsed.kind = RequestKind::kLatestV1;
    return parsed;
  }

  if (text == kBoundaryNoteRequest) {
    SnapshotRequest parsed;
    parsed.kind = RequestKind::kNoteBoundaryV1;
    return parsed;
  }

  const std::string_view kill_prefix(kKillPrefix);
  if (text.starts_with(kill_prefix) && text.back() == '\n' &&
      text.size() > kill_prefix.size() + 1) {
    const std::string_view id =
        text.substr(kill_prefix.size(), text.size() - kill_prefix.size() - 1);
    if (id.find_first_of(" \t\r\n") == std::string_view::npos) {
      SnapshotRequest parsed;
      parsed.kind = RequestKind::kNoteKilledV1;
      parsed.catalogue_id.assign(id);
      return parsed;
    }
  }

  const std::string_view prefix(kBoundaryPrefix);
  if (!text.starts_with(prefix) || text.size() <= prefix.size() + 1) return {};
  if (text.back() != '\n') return {};
  const std::string_view digits =
      text.substr(prefix.size(), text.size() - prefix.size() - 1);

  SnapshotRequest parsed;
  if (!ParseBoundaryEpoch(digits, &parsed.boundary_epoch)) return {};
  parsed.kind = RequestKind::kBoundaryCaptureV2;
  return parsed;
}

void SendAll(SOCKET client, const std::string& response) {
  std::size_t sent_total = 0;
  while (sent_total < response.size()) {
    const int sent = send(client, response.data() + sent_total,
                          static_cast<int>(response.size() - sent_total), 0);
    if (sent <= 0) return;
    sent_total += static_cast<std::size_t>(sent);
  }
}

struct NornirClient {
  SOCKET socket;
  std::uint64_t nonce;
  NornirCapturer capturer;
  const char* unavailable;
};

unsigned __stdcall ServeNornir(void* raw) {
  std::unique_ptr<NornirClient> client(static_cast<NornirClient*>(raw));
  try {
    const auto epoch = CurrentRestoreEpochInternal();
    const auto response = client->capturer(client->nonce, epoch);
    SendAll(client->socket, epoch == CurrentRestoreEpochInternal() && response.size() <= 4096 ?
                           response : client->unavailable);
  } catch (...) {
    SendAll(client->socket, client->unavailable);
  }
  shutdown(client->socket, SD_BOTH);
  closesocket(client->socket);
  g_nornir_busy.store(false);
  return 0;
}

bool DispatchNornir(SOCKET socket, std::uint64_t nonce, NornirCapturer capturer,
                    const char* unavailable) {
  if (!capturer || g_nornir_busy.exchange(true)) return false;
  auto* client = new (std::nothrow) NornirClient{socket, nonce, capturer, unavailable};
  const auto thread = client ? _beginthreadex(nullptr, 0, ServeNornir, client, 0, nullptr) : 0;
  if (!thread) { delete client; g_nornir_busy.store(false); return false; }
  CloseHandle(reinterpret_cast<HANDLE>(thread));
  return true;
}

unsigned __stdcall ServeSnapshots(void* raw_listener) {
  const SOCKET listener = static_cast<SOCKET>(
      reinterpret_cast<std::uintptr_t>(raw_listener));
  g_server_state.store(ServerState::kRunning);
  AppendBridgeLog(
      "RAVEN_NATIVE_BRIDGE_DELIVERY_READY mechanism=loopback_socket "
      "address=127.0.0.1 port=" + std::to_string(kSnapshotDeliveryPort) +
      " static_descriptor_writes=false save_writes=false progression_writes=false");
  for (;;) {
    SOCKET client = accept(listener, nullptr, nullptr);
    if (client == INVALID_SOCKET) continue;
    setsockopt(client, SOL_SOCKET, SO_RCVTIMEO,
               reinterpret_cast<const char*>(&kClientTimeoutMs),
               sizeof(kClientTimeoutMs));
    setsockopt(client, SOL_SOCKET, SO_SNDTIMEO,
               reinterpret_cast<const char*>(&kClientTimeoutMs),
               sizeof(kClientTimeoutMs));
    const SnapshotRequest request = ReceiveRequest(client);
    if (request.kind == RequestKind::kInvalid) {
      SendAll(client, "RAVEN_SNAPSHOT ERROR request\n");
      closesocket(client);
      continue;
    }

    NativeRavenSnapshot snapshot;
    if (request.kind == RequestKind::kCollectibleCaptureV1) {
      if (DispatchNornir(client, request.boundary_epoch, g_collectible_capturer,
                        "COLLECTIBLE_SNAPSHOT_V1 UNAVAILABLE\n")) continue;
      SendAll(client, "COLLECTIBLE_SNAPSHOT_V1 UNAVAILABLE\n");
    } else if (request.kind == RequestKind::kNornirCaptureV1) {
      // One bounded worker keeps slow chest decode off Raven's request loop.
      if (DispatchNornir(client, request.boundary_epoch, g_nornir_capturer,
                        "NORNIR_SNAPSHOT_V1 UNAVAILABLE\n")) continue;
      SendAll(client, "NORNIR_SNAPSHOT_V1 UNAVAILABLE\n");
    } else if (request.kind == RequestKind::kLatestV1) {
      // Never serve the publication store before attempting a fresh capture.
      // A different save can make the previously published image stale while
      // the new staged WAD table is still partial. Fresh partial evidence must
      // win over any prior process-local snapshot.
      bool full_available =
          g_snapshot_capturer != nullptr && g_snapshot_capturer(&snapshot);
      if (full_available) {
        const BaseObservation observation =
            ObserveAuthoritativeBaseInternal(snapshot, GetTickCount64(), false);
        if (observation.inferred_boundary) {
          AppendBridgeLog(
              "RAVEN_NATIVE_BRIDGE_BOUNDARY_NOTED restoreEpoch=" +
              std::to_string(observation.restore_epoch) +
              " advanced=true source=authoritative_revive revived=" +
              std::to_string(observation.revived_count) +
              " save_writes=false progression_writes=false");
        }
        snapshot = MergeCurrentEpochKillsInternal(snapshot);
        SendAll(client, BuildRavenSnapshotWireResponse(
                            snapshot, observation.restore_epoch));
      } else if (snapshot.partial_usable) {
        const std::uint64_t restore_epoch = CurrentRestoreEpochInternal();
        snapshot = MergeCurrentEpochKillsInternal(snapshot);
        AppendBridgeLog(
            "RAVEN_NATIVE_BRIDGE_PARTIAL_SNAPSHOT restoreEpoch=" +
            std::to_string(restore_epoch) +
            " unknown=" + std::to_string(snapshot.unknown_count) +
            " knownKilled=" + std::to_string(snapshot.killed_count) +
            " knownAlive=" + std::to_string(snapshot.alive_count) +
            " readOnly=true save_writes=false progression_writes=false");
        SendAll(client, BuildRavenPartialSnapshotWireResponse(
                            snapshot, restore_epoch));
      } else {
        SendAll(client, "RAVEN_SNAPSHOT_V1 UNAVAILABLE\n");
      }
    } else if (request.kind == RequestKind::kBoundaryCaptureV2) {
      const std::uint64_t restore_epoch = CurrentRestoreEpochInternal();
      if (request.boundary_epoch != restore_epoch) {
        SendAll(client,
                "RAVEN_SNAPSHOT_V2 UNAVAILABLE boundaryEpoch=" +
                    std::to_string(request.boundary_epoch) +
                    " currentRestoreEpoch=" + std::to_string(restore_epoch) +
                    "\n");
      } else {
        const bool captured =
            g_snapshot_capturer != nullptr && g_snapshot_capturer(&snapshot);
        if (captured) {
          const BaseObservation observation =
              ObserveAuthoritativeBaseInternal(snapshot, GetTickCount64(), true);
          if (observation.restore_epoch != request.boundary_epoch) {
            SendAll(client,
                    "RAVEN_SNAPSHOT_V2 UNAVAILABLE boundaryEpoch=" +
                        std::to_string(request.boundary_epoch) +
                        " currentRestoreEpoch=" +
                        std::to_string(observation.restore_epoch) + "\n");
          } else {
            CacheBoundarySnapshotInternal(snapshot, request.boundary_epoch);
            snapshot = MergeCurrentEpochKillsInternal(snapshot);
            SendAll(client, BuildRavenBoundarySnapshotWireResponse(
                                snapshot, request.boundary_epoch));
          }
        } else if (ReadBoundarySnapshotInternal(request.boundary_epoch,
                                                &snapshot)) {
          AppendBridgeLog(
              "RAVEN_NATIVE_BRIDGE_BOUNDARY_CACHE_HIT boundaryEpoch=" +
              std::to_string(request.boundary_epoch) +
              " generation=" + std::to_string(snapshot.generation) +
              " save_writes=false progression_writes=false");
          snapshot = MergeCurrentEpochKillsInternal(snapshot);
          SendAll(client, BuildRavenBoundarySnapshotWireResponse(
                              snapshot, request.boundary_epoch));
        } else if (snapshot.partial_usable) {
          snapshot = MergeCurrentEpochKillsInternal(snapshot);
          AppendBridgeLog(
              "RAVEN_NATIVE_BRIDGE_PARTIAL_BOUNDARY_SNAPSHOT boundaryEpoch=" +
              std::to_string(request.boundary_epoch) +
              " unknown=" + std::to_string(snapshot.unknown_count) +
              " knownKilled=" + std::to_string(snapshot.killed_count) +
              " knownAlive=" + std::to_string(snapshot.alive_count) +
              " readOnly=true save_writes=false progression_writes=false");
          SendAll(client, BuildRavenPartialBoundarySnapshotWireResponse(
                              snapshot, request.boundary_epoch));
        } else {
          SendAll(client,
                  "RAVEN_SNAPSHOT_V2 UNAVAILABLE boundaryEpoch=" +
                      std::to_string(request.boundary_epoch) + "\n");
        }
      }
    } else if (request.kind == RequestKind::kNoteKilledV1) {
      std::uint64_t restore_epoch = 0;
      if (!NoteKilledInternal(request.catalogue_id, &restore_epoch)) {
        SendAll(client, "RAVEN_NOTE_V1 ERROR unknown_catalogue_id\n");
      } else {
        AppendBridgeLog(
            "RAVEN_NATIVE_BRIDGE_KILL_NOTED catalogueId=" +
            request.catalogue_id + " restoreEpoch=" +
            std::to_string(restore_epoch) +
            " save_writes=false progression_writes=false");
        SendAll(client,
                "RAVEN_NOTE_V1 OK kind=killed restoreEpoch=" +
                    std::to_string(restore_epoch) + "\n");
      }
    } else {
      bool advanced = false;
      const std::uint64_t restore_epoch =
          NoteRestoreBoundaryInternal(GetTickCount64(), &advanced);
      AppendBridgeLog(
          "RAVEN_NATIVE_BRIDGE_BOUNDARY_NOTED restoreEpoch=" +
          std::to_string(restore_epoch) +
          " advanced=" + (advanced ? std::string("true") : std::string("false")) +
          " source=checkpoint save_writes=false progression_writes=false");
      SendAll(client,
              "RAVEN_NOTE_V1 OK kind=boundary restoreEpoch=" +
                  std::to_string(restore_epoch) +
                  " advanced=" + (advanced ? std::string("true") : std::string("false")) +
                  "\n");
    }
    shutdown(client, SD_BOTH);
    closesocket(client);
  }
}

}  // namespace

std::string BuildRavenSnapshotWireResponse(
    const NativeRavenSnapshot& snapshot, std::uint64_t restore_epoch) {
  std::string killed_ids;
  for (std::size_t index = 0; index < kRavenCatalogue.size(); ++index) {
    if (!snapshot.killed[index]) continue;
    if (!killed_ids.empty()) killed_ids.push_back(',');
    killed_ids.append(kRavenCatalogue[index].catalogue_id);
  }
  if (killed_ids.empty()) killed_ids = "-";
  return "RAVEN_SNAPSHOT_V1 schema=1 restoreEpoch=" +
         std::to_string(restore_epoch) + " generation=" +
         std::to_string(snapshot.generation) + " capturedTickMs=" +
         std::to_string(snapshot.captured_tick_ms) + " count=53 unknown=0 alive=" +
         std::to_string(snapshot.alive_count) + " killed=" +
         std::to_string(snapshot.killed_count) + " explicit=" +
         std::to_string(snapshot.explicit_count) + " absentWadFalse=" +
         std::to_string(snapshot.absence_default_false_count) + " killedIds=" +
         killed_ids + "\n";
}

std::string BuildRavenBoundarySnapshotWireResponse(
    const NativeRavenSnapshot& snapshot, std::uint64_t boundary_epoch) {
  std::string killed_ids;
  for (std::size_t index = 0; index < kRavenCatalogue.size(); ++index) {
    if (!snapshot.killed[index]) continue;
    if (!killed_ids.empty()) killed_ids.push_back(',');
    killed_ids.append(kRavenCatalogue[index].catalogue_id);
  }
  if (killed_ids.empty()) killed_ids = "-";
  return "RAVEN_SNAPSHOT_V2 schema=2 boundaryEpoch=" +
         std::to_string(boundary_epoch) + " generation=" +
         std::to_string(snapshot.generation) + " capturedTickMs=" +
         std::to_string(snapshot.captured_tick_ms) +
         " count=53 unknown=0 alive=" +
         std::to_string(snapshot.alive_count) + " killed=" +
         std::to_string(snapshot.killed_count) + " explicit=" +
         std::to_string(snapshot.explicit_count) + " absentWadFalse=" +
         std::to_string(snapshot.absence_default_false_count) + " killedIds=" +
         killed_ids + "\n";
}

namespace {

std::string BuildPartialWireResponse(
    const NativeRavenSnapshot& snapshot, std::string_view header,
    std::string_view epoch_key, std::uint64_t epoch) {
  std::string killed_ids;
  std::string unknown_ids;
  std::string absence_ids;
  for (std::size_t index = 0; index < kRavenCatalogue.size(); ++index) {
    if (snapshot.absence_default_state[index]) {
      if (!absence_ids.empty()) absence_ids.push_back(',');
      absence_ids.append(kRavenCatalogue[index].catalogue_id);
    }
    if (!snapshot.known[index]) {
      if (!unknown_ids.empty()) unknown_ids.push_back(',');
      unknown_ids.append(kRavenCatalogue[index].catalogue_id);
      continue;
    }
    if (!snapshot.killed[index]) continue;
    if (!killed_ids.empty()) killed_ids.push_back(',');
    killed_ids.append(kRavenCatalogue[index].catalogue_id);
  }
  if (killed_ids.empty()) killed_ids = "-";
  if (unknown_ids.empty()) unknown_ids = "-";
  if (absence_ids.empty()) absence_ids = "-";
  return std::string(header) + " schema=" +
         (header == "RAVEN_SNAPSHOT_V2 PARTIAL" ? "2 " : "1 ") +
         std::string(epoch_key) + "=" + std::to_string(epoch) +
         " capturedTickMs=" + std::to_string(snapshot.captured_tick_ms) +
         " count=53 unknown=" + std::to_string(snapshot.unknown_count) +
         " alive=" + std::to_string(snapshot.alive_count) +
         " killed=" + std::to_string(snapshot.killed_count) +
         " explicit=" + std::to_string(snapshot.explicit_count) +
         " absentWadFalse=" +
         std::to_string(snapshot.absence_default_false_count) +
         " killedIds=" + killed_ids + " unknownIds=" + unknown_ids +
         " absenceIds=" + absence_ids + "\n";
}

}  // namespace

std::string BuildRavenPartialSnapshotWireResponse(
    const NativeRavenSnapshot& snapshot, std::uint64_t restore_epoch) {
  return BuildPartialWireResponse(
      snapshot, "RAVEN_SNAPSHOT_V1 PARTIAL", "restoreEpoch", restore_epoch);
}

std::string BuildRavenPartialBoundarySnapshotWireResponse(
    const NativeRavenSnapshot& snapshot, std::uint64_t boundary_epoch) {
  return BuildPartialWireResponse(
      snapshot, "RAVEN_SNAPSHOT_V2 PARTIAL", "boundaryEpoch", boundary_epoch);
}

bool StartSnapshotDeliveryServer(SnapshotReader reader,
                                 SnapshotCapturer capturer,
                                 NornirCapturer nornir_capturer,
                                 NornirCapturer collectible_capturer) {
  if (reader == nullptr || capturer == nullptr) return false;
  ServerState expected = ServerState::kNotStarted;
  if (!g_server_state.compare_exchange_strong(expected,
                                               ServerState::kStarting)) {
    return expected == ServerState::kStarting ||
           (expected == ServerState::kRunning &&
            g_snapshot_reader == reader &&
            g_snapshot_capturer == capturer && g_nornir_capturer == nornir_capturer &&
            g_collectible_capturer == collectible_capturer);
  }
  g_snapshot_reader = reader;
  g_snapshot_capturer = capturer;
  g_nornir_capturer = nornir_capturer;
  g_collectible_capturer = collectible_capturer;
  int error = 0;
  const SOCKET listener = OpenListener(kSnapshotDeliveryPort, nullptr, &error);
  if (listener == INVALID_SOCKET) {
    g_server_state.store(ServerState::kRefused);
    AppendBridgeLog(
        "RAVEN_NATIVE_BRIDGE_DELIVERY_REFUSED reason=loopback_bind_failed:" +
        std::to_string(error) + " static_descriptor_writes=false");
    return false;
  }
  const uintptr_t thread = _beginthreadex(
      nullptr, 0, ServeSnapshots,
      reinterpret_cast<void*>(static_cast<std::uintptr_t>(listener)), 0,
      nullptr);
  if (thread == 0) {
    closesocket(listener);
    g_server_state.store(ServerState::kRefused);
    AppendBridgeLog(
        "RAVEN_NATIVE_BRIDGE_DELIVERY_REFUSED reason=thread_start_failed "
        "static_descriptor_writes=false");
    return false;
  }
  CloseHandle(reinterpret_cast<HANDLE>(thread));
  return true;
}

namespace delivery_test {

std::uintptr_t OpenLoopbackListener(std::uint16_t port,
                                    std::uint16_t* bound_port,
                                    int* error) {
  const SOCKET listener = OpenListener(port, bound_port, error);
  if (listener == INVALID_SOCKET) return kInvalidListener;
  return static_cast<std::uintptr_t>(listener);
}

void CloseLoopbackListener(std::uintptr_t listener) {
  if (listener != kInvalidListener) closesocket(static_cast<SOCKET>(listener));
}

void ResetSessionAuthority() {
  std::lock_guard<std::mutex> lock(g_session_mutex);
  g_restore_epoch = 0;
  g_last_boundary_note_ms = 0;
  g_have_boundary_note = false;
  g_kill_epochs.fill(0);
  g_kill_noted.fill(false);
  g_have_authoritative_base = false;
  g_last_authoritative_killed.fill(false);
  g_last_authoritative_epoch = 0;
  ClearBoundarySnapshotLocked();
}

std::uint64_t NoteRestoreBoundary(std::uint64_t now_ms) {
  return NoteRestoreBoundaryInternal(now_ms, nullptr);
}

bool NoteKilled(std::string_view catalogue_id) {
  return NoteKilledInternal(catalogue_id, nullptr);
}

std::uint64_t CurrentRestoreEpoch() {
  return CurrentRestoreEpochInternal();
}

std::uint64_t ObserveAuthoritativeBase(
    const NativeRavenSnapshot& snapshot, std::uint64_t now_ms) {
  return ObserveAuthoritativeBaseInternal(snapshot, now_ms, false).restore_epoch;
}

NativeRavenSnapshot MergeCurrentEpochKills(
    const NativeRavenSnapshot& snapshot) {
  return MergeCurrentEpochKillsInternal(snapshot);
}

void CacheBoundarySnapshot(
    const NativeRavenSnapshot& snapshot, std::uint64_t boundary_epoch) {
  CacheBoundarySnapshotInternal(snapshot, boundary_epoch);
}

bool ReadBoundarySnapshot(
    std::uint64_t boundary_epoch, NativeRavenSnapshot* snapshot) {
  return ReadBoundarySnapshotInternal(boundary_epoch, snapshot);
}

}  // namespace delivery_test
}  // namespace completionist
