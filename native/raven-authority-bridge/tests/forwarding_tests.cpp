#include <windows.h>
#include <Xinput.h>

#include <iostream>

namespace {

using XInputGetStateFn = DWORD(WINAPI*)(DWORD, XINPUT_STATE*);

int Fail(const char* message) {
  std::cerr << "FAIL: " << message << '\n';
  return 1;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  if (argc != 2) {
    return Fail("expected proxy DLL path");
  }
  HMODULE proxy = LoadLibraryExW(argv[1], nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
  if (proxy == nullptr) {
    return Fail("proxy DLL did not load");
  }
  auto get_state = reinterpret_cast<XInputGetStateFn>(
      GetProcAddress(proxy, "XInputGetState"));
  FARPROC ordinal_state = GetProcAddress(proxy, MAKEINTRESOURCEA(2));
  if (get_state == nullptr || reinterpret_cast<FARPROC>(get_state) != ordinal_state) {
    return Fail("proxy export missing");
  }
  XINPUT_STATE state{};
  const DWORD result = get_state(0, &state);
  if (result != ERROR_SUCCESS && result != ERROR_DEVICE_NOT_CONNECTED) {
    return Fail("forwarded XInputGetState returned unexpected error");
  }
  // Test host fails exe gate. Let worker log rejection before process teardown.
  Sleep(1000);
  std::cout << "RAVEN_BRIDGE_FORWARDING_TEST_PASSED target=XINPUT1_4.dll\n";
  return 0;
}
