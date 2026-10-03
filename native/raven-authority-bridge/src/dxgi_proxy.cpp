#include <windows.h>

#include <process.h>

#include <array>
#include <atomic>
#include <cstdint>
#include <string>

#include "authority_runtime.h"
#include "dxgi_contract.generated.h"
#include "dxgi_forwarding.h"
#include "platform.h"

namespace {

INIT_ONCE g_dxgi_once = INIT_ONCE_STATIC_INIT;
HMODULE g_real_dxgi = nullptr;
std::array<FARPROC, completionist::kDxgiExports.size()> g_exports{};
DWORD g_dxgi_error = ERROR_SUCCESS;
std::atomic<bool> g_worker_started{false};

extern "C" HRESULT WINAPI CompletionistDxgiForwardingFailure() {
  const DWORD error =
      g_dxgi_error == ERROR_SUCCESS ? ERROR_PROC_NOT_FOUND : g_dxgi_error;
  return HRESULT_FROM_WIN32(error);
}

FARPROC FailureAddress() {
  return reinterpret_cast<FARPROC>(&CompletionistDxgiForwardingFailure);
}

BOOL CALLBACK ResolveRealDxgi(PINIT_ONCE, PVOID, PVOID*) {
  std::wstring path;
  if (!completionist::BuildSystemDxgiPath(&path, &g_dxgi_error)) {
    return TRUE;
  }
  const std::wstring system_directory = path.substr(0, path.find_last_of(L"\\/"));
  if (!completionist::IsPathInsideDirectory(path, system_directory)) {
    g_dxgi_error = ERROR_INVALID_NAME;
    return TRUE;
  }
  g_real_dxgi = LoadLibraryExW(path.c_str(), nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (g_real_dxgi == nullptr) {
    g_dxgi_error = GetLastError();
    return TRUE;
  }
  completionist::ResolveDxgiExportsByName(g_real_dxgi, &g_exports, &g_dxgi_error);
  return TRUE;
}

unsigned __stdcall InitializeBridge(void*) {
  completionist::RunAuthorityWorker();
  return 0;
}

void StartWorkerOnce() {
  bool expected = false;
  if (!g_worker_started.compare_exchange_strong(expected, true)) {
    return;
  }
  completionist::SetProxyForwardReady(true);
  const uintptr_t worker =
      _beginthreadex(nullptr, 0, InitializeBridge, nullptr, 0, nullptr);
  if (worker != 0) {
    CloseHandle(reinterpret_cast<HANDLE>(worker));
  }
}

}  // namespace

extern "C" FARPROC CompletionistResolveDxgiExport(unsigned int ordinal) {
  InitOnceExecuteOnce(&g_dxgi_once, ResolveRealDxgi, nullptr, nullptr);
  if (g_dxgi_error != ERROR_SUCCESS) {
    return FailureAddress();
  }
  for (std::size_t index = 0; index < completionist::kDxgiExports.size();
       ++index) {
    if (completionist::kDxgiExports[index].ordinal == ordinal) {
      if (g_exports[index] == nullptr) return FailureAddress();
      StartWorkerOnce();
      return g_exports[index];
    }
  }
  return FailureAddress();
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    DisableThreadLibraryCalls(instance);
  }
  return TRUE;
}
