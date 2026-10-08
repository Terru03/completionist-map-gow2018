#include <windows.h>

extern "C" void WINAPI CompletionistDxgiThunk8(SIZE_T, const char*);

namespace {
BOOL WINAPI BeforeCrt(HINSTANCE, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    // MSVC invokes this callback before initializing this DLL's static CRT.
    // Emulate the loader's early SetAppCompatStringPointer call without relying
    // on the host Windows version's compatibility-shim implementation.
    CompletionistDxgiThunk8(0, nullptr);
  }
  return TRUE;
}
}

extern "C" BOOL (WINAPI* const _pRawDllMain)(HINSTANCE, DWORD, LPVOID) = BeforeCrt;
