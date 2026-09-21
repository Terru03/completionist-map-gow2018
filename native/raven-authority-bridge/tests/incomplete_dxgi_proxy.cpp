#include <windows.h>

extern "C" HRESULT WINAPI IncompleteCreateFactory(REFIID, void**) {
  return E_NOTIMPL;
}

extern "C" BOOL WINAPI IncompleteSnapshot(void*) {
  return FALSE;
}

BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID) {
  return TRUE;
}
