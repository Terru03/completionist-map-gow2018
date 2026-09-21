#include <windows.h>
#include <dxgi.h>

#include <iostream>

namespace {

using CreateDxgiFactory1Fn = HRESULT(WINAPI*)(REFIID, void**);

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
  auto create_factory = reinterpret_cast<CreateDxgiFactory1Fn>(
      GetProcAddress(proxy, "CreateDXGIFactory1"));
  if (create_factory == nullptr) {
    return Fail("proxy export missing");
  }
  IDXGIFactory1* factory = nullptr;
  const HRESULT result = create_factory(__uuidof(IDXGIFactory1),
                                        reinterpret_cast<void**>(&factory));
  if (FAILED(result) || factory == nullptr) {
    return Fail("forwarded CreateDXGIFactory1 failed");
  }
  factory->Release();
  std::cout << "RAVEN_BRIDGE_FORWARDING_TEST_PASSED\n";
  return 0;
}
