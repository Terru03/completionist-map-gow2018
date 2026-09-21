#include <windows.h>

#include <cwchar>
#include <iostream>
#include <string>

#include "platform.h"

namespace {

int Fail(const char* message) {
  std::cerr << "FAIL: " << message << '\n';
  return 1;
}

}  // namespace

int wmain() {
  std::wstring dxgi_path;
  DWORD error = ERROR_SUCCESS;
  if (!completionist::BuildSystemDxgiPath(&dxgi_path, &error)) {
    return Fail("BuildSystemDxgiPath failed");
  }
  std::wstring system_directory = dxgi_path.substr(
      0, dxgi_path.find_last_of(L"\\/"));
  if (!completionist::IsPathInsideDirectory(dxgi_path, system_directory)) {
    return Fail("DXGI path escaped System32");
  }
  const wchar_t* basename = std::wcsrchr(dxgi_path.c_str(), L'\\');
  if (basename == nullptr || _wcsicmp(basename + 1, L"dxgi.dll") != 0) {
    return Fail("DXGI basename wrong");
  }
  HMODULE real_dxgi = LoadLibraryExW(dxgi_path.c_str(), nullptr,
                                     LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (real_dxgi == nullptr) {
    return Fail("real System32 DXGI did not load");
  }
  FARPROC export_address = GetProcAddress(real_dxgi, "CreateDXGIFactory1");
  FreeLibrary(real_dxgi);
  if (export_address == nullptr) {
    return Fail("real DXGI export missing");
  }
  if (completionist::IsPathInsideDirectory(L"C:\\Windows\\System32evil\\dxgi.dll",
                                            L"C:\\Windows\\System32")) {
    return Fail("directory boundary check accepted sibling prefix");
  }
  std::cout << "RAVEN_BRIDGE_PLATFORM_TESTS_PASSED\n";
  return 0;
}
