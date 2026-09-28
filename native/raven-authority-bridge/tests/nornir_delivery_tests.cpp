#include <winsock2.h>
#include <ws2tcpip.h>
#include "snapshot_delivery.h"
#include <iostream>
#include <stdexcept>

using namespace completionist;
HANDLE entered = nullptr;
HANDLE release_capture = nullptr;
void Check(bool value, const char* reason) { if (!value) throw std::runtime_error(reason); }
bool Raven(NativeRavenSnapshot* snapshot) {
  snapshot->alive_count = 53;
  snapshot->known.fill(true);
  snapshot->generation = 1;
  return true;
}
std::string SlowNornir(std::uint64_t nonce, std::uint64_t epoch) {
  SetEvent(entered);
  Check(WaitForSingleObject(release_capture, 4000) == WAIT_OBJECT_0, "capture release timeout");
  return "NORNIR_SNAPSHOT_V1 nonce=" + std::to_string(nonce) +
         " restoreEpoch=" + std::to_string(epoch) + "\n";
}
SOCKET Request(const std::string& request) {
  SOCKET client = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  Check(client != INVALID_SOCKET, "socket failed");
  const int timeout = 1000;
  setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&timeout), sizeof(timeout));
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  address.sin_port = htons(kSnapshotDeliveryPort);
  Check(connect(client, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0, "connect failed");
  Check(send(client, request.data(), static_cast<int>(request.size()), 0) == static_cast<int>(request.size()), "send failed");
  return client;
}
std::string Response(SOCKET client) {
  std::string result;
  char ch = 0;
  while (result.size() < 4096) {
    Check(recv(client, &ch, 1, 0) == 1, "response blocked or closed");
    result += ch;
    if (ch == '\n') { closesocket(client); return result; }
  }
  closesocket(client);
  throw std::runtime_error("response cap");
}
int main() {
  try {
    entered = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    release_capture = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    Check(entered && release_capture, "event failed");
    Check(StartSnapshotDeliveryServer(Raven, Raven, SlowNornir), "listener unavailable");
    const auto chest = Request("CAPTURE NORNIR_SNAPSHOT_V1 nonce=7\n");
    Check(WaitForSingleObject(entered, 1000) == WAIT_OBJECT_0, "capture never started");
    Check(Response(Request("GET RAVEN_SNAPSHOT_V1\n")).starts_with("RAVEN_SNAPSHOT_V1 schema=1"),
          "slow Nornir capture blocked Raven reply");
    Check(Response(Request("CAPTURE NORNIR_SNAPSHOT_V1 nonce=8\n")) == "NORNIR_SNAPSHOT_V1 UNAVAILABLE\n",
          "more than one Nornir worker accepted");
    Check(Response(Request("NOTE RAVEN_BOUNDARY_V1 source=checkpoint\n")).starts_with("RAVEN_NOTE_V1 OK"),
          "slow capture blocked boundary");
    SetEvent(release_capture);
    Check(Response(chest) == "NORNIR_SNAPSHOT_V1 UNAVAILABLE\n", "old boundary response escaped");
    CloseHandle(entered); CloseHandle(release_capture);
    std::cout << "NORNIR_DELIVERY_PASS raven_unblocked worker_bounded stale_epoch_rejected\n";
    return 0;
  } catch (const std::exception& error) {
    if (release_capture) SetEvent(release_capture);
    std::cerr << error.what() << '\n'; return 1;
  }
}
