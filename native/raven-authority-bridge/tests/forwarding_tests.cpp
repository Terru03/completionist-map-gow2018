#include <windows.h>
#include <dxgi1_2.h>
#include <psapi.h>

#include <algorithm>
#include <array>
#include <cwctype>
#include <iostream>
#include <string>

#include "dxgi_contract.generated.h"

namespace {

using CreateFactoryFn = HRESULT(WINAPI*)(REFIID, void**);
using CreateFactory2Fn = HRESULT(WINAPI*)(UINT, REFIID, void**);

int Fail(const char* message) {
  std::cerr << "FAIL: " << message << '\n';
  return 1;
}

std::wstring Lower(std::wstring value) {
  std::transform(value.begin(), value.end(), value.begin(),
                 [](wchar_t ch) { return static_cast<wchar_t>(towlower(ch)); });
  return value;
}

bool CallFactory(FARPROC address, REFIID iid) {
  auto function = reinterpret_cast<CreateFactoryFn>(address);
  void* object = nullptr;
  const HRESULT result = function(iid, &object);
  if (FAILED(result) || object == nullptr) return false;
  static_cast<IUnknown*>(object)->Release();
  return true;
}

bool CallFactory2(FARPROC address) {
  auto function = reinterpret_cast<CreateFactory2Fn>(address);
  void* object = nullptr;
  const HRESULT result = function(0, __uuidof(IDXGIFactory2), &object);
  if (FAILED(result) || object == nullptr) return false;
  static_cast<IUnknown*>(object)->Release();
  return true;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  if (argc != 2) return Fail("expected proxy DLL path");

  std::array<wchar_t, MAX_PATH> temp_root{};
  if (GetTempPathW(static_cast<DWORD>(temp_root.size()), temp_root.data()) == 0) {
    return Fail("temporary directory lookup failed");
  }
  const std::wstring test_directory =
      std::wstring(temp_root.data()) + L"completionist-dxgi-load-" +
      std::to_wstring(GetCurrentProcessId()) + L"-" +
      std::to_wstring(GetTickCount64());
  if (!CreateDirectoryW(test_directory.c_str(), nullptr)) {
    return Fail("test directory creation failed");
  }
  const std::wstring proxy_path = test_directory + L"\\dxgi.dll";
  if (!CopyFileW(argv[1], proxy_path.c_str(), TRUE)) {
    RemoveDirectoryW(test_directory.c_str());
    return Fail("proxy copy into test directory failed");
  }
  HMODULE proxy = LoadLibraryExW(proxy_path.c_str(), nullptr,
                                 LOAD_WITH_ALTERED_SEARCH_PATH);
  if (proxy == nullptr) return Fail("proxy DLL did not load from test directory");

  for (const auto& spec : completionist::kDxgiExports) {
    const std::string name(spec.name);
    FARPROC by_name = GetProcAddress(proxy, name.c_str());
    FARPROC by_ordinal = GetProcAddress(
        proxy, MAKEINTRESOURCEA(static_cast<WORD>(spec.ordinal)));
    if (by_name == nullptr || by_name != by_ordinal) {
      return Fail("full proxy contract did not resolve by name and ordinal");
    }
  }

  struct FactorySpec {
    const char* name;
    WORD ordinal;
  };
  constexpr std::array<FactorySpec, 3> factories{{
      {"CreateDXGIFactory", 10},
      {"CreateDXGIFactory1", 11},
      {"CreateDXGIFactory2", 12},
  }};
  std::array<FARPROC, factories.size()> addresses{};
  for (std::size_t index = 0; index < factories.size(); ++index) {
    addresses[index] = GetProcAddress(proxy, factories[index].name);
    FARPROC ordinal = GetProcAddress(
        proxy, MAKEINTRESOURCEA(factories[index].ordinal));
    if (addresses[index] == nullptr || addresses[index] != ordinal) {
      return Fail("representative factory name/ordinal resolve failed");
    }
  }
  FARPROC snapshot = GetProcAddress(proxy, "CompletionistMapGetRavenSnapshotV1");
  if (snapshot == nullptr ||
      snapshot != GetProcAddress(proxy, MAKEINTRESOURCEA(
                                          completionist::kSnapshotExportOrdinal))) {
    return Fail("snapshot API missing");
  }
  if (!CallFactory(addresses[0], __uuidof(IDXGIFactory)) ||
      !CallFactory(addresses[1], __uuidof(IDXGIFactory1)) ||
      !CallFactory2(addresses[2])) {
    return Fail("safe factory forwarding failed");
  }

  std::array<wchar_t, MAX_PATH> system_directory{};
  if (GetSystemDirectoryW(system_directory.data(),
                          static_cast<UINT>(system_directory.size())) == 0) {
    return Fail("System32 path lookup failed");
  }
  const std::wstring expected_system =
      Lower(std::wstring(system_directory.data()) + L"\\dxgi.dll");
  const std::wstring expected_proxy = Lower(proxy_path);
  std::array<HMODULE, 2048> modules{};
  DWORD needed = 0;
  if (!EnumProcessModules(GetCurrentProcess(), modules.data(),
                          static_cast<DWORD>(sizeof(modules)), &needed) ||
      needed > sizeof(modules)) {
    return Fail("module enumeration failed");
  }
  bool proxy_seen = false;
  bool system_seen = false;
  const std::size_t count = needed / sizeof(HMODULE);
  for (std::size_t index = 0; index < count; ++index) {
    std::array<wchar_t, 32768> path{};
    if (GetModuleFileNameExW(GetCurrentProcess(), modules[index], path.data(),
                             static_cast<DWORD>(path.size())) == 0) {
      continue;
    }
    const std::wstring normalized = Lower(path.data());
    proxy_seen = proxy_seen || normalized == expected_proxy;
    system_seen = system_seen || normalized == expected_system;
  }
  if (!proxy_seen || !system_seen || expected_proxy == expected_system) {
    return Fail("explicit System32 DXGI load or no-recursion proof failed");
  }

  Sleep(1000);
  FreeLibrary(proxy);
  DeleteFileW(proxy_path.c_str());
  RemoveDirectoryW(test_directory.c_str());
  std::cout << "RAVEN_BRIDGE_FORWARDING_TEST_PASSED target=dxgi.dll "
               "factories=3 system32_loaded=true recursion=false\n";
  return 0;
}
