#include <windows.h>

#include <process.h>

#include <atomic>
#include <string>

#include "authority_runtime.h"
#include "platform.h"

namespace {

using CreateDxgiFactory1Fn = HRESULT(WINAPI*)(REFIID, void**);

INIT_ONCE g_dxgi_once = INIT_ONCE_STATIC_INIT;
HMODULE g_real_dxgi = nullptr;
CreateDxgiFactory1Fn g_create_factory = nullptr;
DWORD g_dxgi_error = ERROR_SUCCESS;
std::atomic<bool> g_worker_started{false};

BOOL CALLBACK ResolveRealDxgi(PINIT_ONCE, PVOID, PVOID*) {
  std::wstring path;
  if (!completionist::BuildSystemDxgiPath(&path, &g_dxgi_error)) {
    return TRUE;
  }
  std::wstring system_directory = path.substr(0, path.find_last_of(L"\\/"));
  if (!completionist::IsPathInsideDirectory(path, system_directory)) {
    g_dxgi_error = ERROR_INVALID_NAME;
    return TRUE;
  }
  g_real_dxgi = LoadLibraryExW(path.c_str(), nullptr,
                               LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (g_real_dxgi == nullptr) {
    g_dxgi_error = GetLastError();
    return TRUE;
  }
  g_create_factory = reinterpret_cast<CreateDxgiFactory1Fn>(
      GetProcAddress(g_real_dxgi, "CreateDXGIFactory1"));
  if (g_create_factory == nullptr) {
    g_dxgi_error = GetLastError();
    if (g_dxgi_error == ERROR_SUCCESS) {
      g_dxgi_error = ERROR_PROC_NOT_FOUND;
    }
  }
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
  uintptr_t worker = _beginthreadex(nullptr, 0, InitializeBridge, nullptr, 0,
                                    nullptr);
  if (worker != 0) {
    CloseHandle(reinterpret_cast<HANDLE>(worker));
  }
}

HRESULT ForwardingFailure(void** factory) {
  if (factory != nullptr) {
    *factory = nullptr;
  }
  const DWORD error = g_dxgi_error == ERROR_SUCCESS ? ERROR_PROC_NOT_FOUND
                                                     : g_dxgi_error;
  return HRESULT_FROM_WIN32(error);
}

}  // namespace

extern "C" HRESULT WINAPI CompletionistCreateDXGIFactory1(REFIID riid,
                                                            void** factory) {
  InitOnceExecuteOnce(&g_dxgi_once, ResolveRealDxgi, nullptr, nullptr);
  if (g_create_factory == nullptr) {
    return ForwardingFailure(factory);
  }
  const HRESULT result = g_create_factory(riid, factory);
  completionist::SetDxgiForwardResult(result);
  StartWorkerOnce();
  return result;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    DisableThreadLibraryCalls(instance);
  }
  return TRUE;
}
