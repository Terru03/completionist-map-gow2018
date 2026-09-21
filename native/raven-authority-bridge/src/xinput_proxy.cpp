#include <windows.h>

#include <process.h>

#include <array>
#include <atomic>
#include <cstdint>
#include <string>

#include "authority_runtime.h"
#include "platform.h"
#include "xinput_contract.generated.h"

namespace {

INIT_ONCE g_xinput_once = INIT_ONCE_STATIC_INIT;
HMODULE g_real_xinput = nullptr;
std::array<FARPROC, completionist::kXInputExports.size()> g_exports{};
DWORD g_xinput_error = ERROR_SUCCESS;
std::atomic<bool> g_worker_started{false};

FARPROC FailureAddress();

BOOL CALLBACK ResolveRealXInput(PINIT_ONCE, PVOID, PVOID*) {
  std::wstring path;
  if (!completionist::BuildSystemXInputPath(&path, &g_xinput_error)) {
    return TRUE;
  }
  const std::wstring system_directory = path.substr(0, path.find_last_of(L"\\/"));
  if (!completionist::IsPathInsideDirectory(path, system_directory)) {
    g_xinput_error = ERROR_INVALID_NAME;
    return TRUE;
  }
  g_real_xinput =
      LoadLibraryExW(path.c_str(), nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (g_real_xinput == nullptr) {
    g_xinput_error = GetLastError();
    return TRUE;
  }
  for (std::size_t index = 0; index < completionist::kXInputExports.size();
       ++index) {
    const auto& spec = completionist::kXInputExports[index];
    FARPROC by_ordinal = GetProcAddress(
        g_real_xinput, MAKEINTRESOURCEA(static_cast<WORD>(spec.ordinal)));
    if (by_ordinal == nullptr) {
      g_xinput_error = ERROR_PROC_NOT_FOUND;
      return TRUE;
    }
    if (!spec.name.empty()) {
      const std::string name(spec.name);
      FARPROC by_name = GetProcAddress(g_real_xinput, name.c_str());
      if (by_name == nullptr || by_name != by_ordinal) {
        g_xinput_error = ERROR_PROC_NOT_FOUND;
        return TRUE;
      }
    }
    g_exports[index] = by_ordinal;
  }
  g_xinput_error = ERROR_SUCCESS;
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

extern "C" DWORD WINAPI CompletionistXInputForwardingFailure() {
  return g_xinput_error == ERROR_SUCCESS ? ERROR_PROC_NOT_FOUND : g_xinput_error;
}

FARPROC FailureAddress() {
  return reinterpret_cast<FARPROC>(&CompletionistXInputForwardingFailure);
}

}  // namespace

extern "C" FARPROC CompletionistResolveXInputExport(unsigned int ordinal) {
  InitOnceExecuteOnce(&g_xinput_once, ResolveRealXInput, nullptr, nullptr);
  if (g_xinput_error != ERROR_SUCCESS) {
    return FailureAddress();
  }
  for (std::size_t index = 0; index < completionist::kXInputExports.size();
       ++index) {
    if (completionist::kXInputExports[index].ordinal == ordinal) {
      StartWorkerOnce();
      return g_exports[index];
    }
  }
  g_xinput_error = ERROR_PROC_NOT_FOUND;
  return FailureAddress();
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    DisableThreadLibraryCalls(instance);
  }
  return TRUE;
}
