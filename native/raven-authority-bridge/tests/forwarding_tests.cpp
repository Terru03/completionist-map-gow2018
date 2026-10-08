#include <windows.h>
#include <dxgi1_2.h>
#include <psapi.h>

#include <algorithm>
#include <array>
#include <cwctype>
#include <cstring>
#include <iostream>
#include <string>

#include "dxgi_contract.generated.h"

namespace {

using CreateFactoryFn = HRESULT(WINAPI*)(REFIID, void**);
using CreateFactory2Fn = HRESULT(WINAPI*)(UINT, REFIID, void**);
bool simulate_windows10 = false;
bool observe_appcompat = false;
unsigned int appcompat_calls = 0;
SIZE_T appcompat_size = 0;
const char* appcompat_data = nullptr;

void WINAPI ObserveAppCompat(SIZE_T size, const char* data) {
  ++appcompat_calls;
  appcompat_size = size;
  appcompat_data = data;
}

FARPROC WINAPI Windows10Lookup(HMODULE module, LPCSTR name) {
  const auto ordinal = reinterpret_cast<std::uintptr_t>(name);
  if (ordinal > 0xffff && observe_appcompat &&
      std::strcmp(name, "SetAppCompatStringPointer") == 0) {
    return reinterpret_cast<FARPROC>(&ObserveAppCompat);
  }
  if (!simulate_windows10) return GetProcAddress(module, name);
  if (ordinal <= 0xffff) {
    if (ordinal == 18) return GetProcAddress(module, "DXGIGetDebugInterface1");
    if (ordinal == 19) return GetProcAddress(module, "DXGIReportAdapterConfiguration");
    if (ordinal == 20) return nullptr;
  } else if (std::strcmp(name, "DXGIDisableVBlankVirtualization") == 0) {
    return nullptr;
  }
  return GetProcAddress(module, name);
}

bool UseWindows10Lookup(HMODULE module) {
  auto* base = reinterpret_cast<std::uint8_t*>(module);
  const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
  const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
  const auto imports = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
  if (imports.VirtualAddress == 0) return false;
  auto* descriptor = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(base + imports.VirtualAddress);
  for (; descriptor->Name != 0; ++descriptor) {
    if (descriptor->OriginalFirstThunk == 0) continue;
    auto* names = reinterpret_cast<IMAGE_THUNK_DATA64*>(base + descriptor->OriginalFirstThunk);
    auto* addresses = reinterpret_cast<IMAGE_THUNK_DATA64*>(base + descriptor->FirstThunk);
    for (; names->u1.AddressOfData != 0; ++names, ++addresses) {
      if (IMAGE_SNAP_BY_ORDINAL64(names->u1.Ordinal)) continue;
      const auto* import = reinterpret_cast<const IMAGE_IMPORT_BY_NAME*>(base + names->u1.AddressOfData);
      if (std::strcmp(import->Name, "GetProcAddress") != 0) continue;
      DWORD protection = 0;
      if (!VirtualProtect(&addresses->u1.Function, sizeof(addresses->u1.Function),
                          PAGE_READWRITE, &protection)) return false;
      addresses->u1.Function = reinterpret_cast<ULONG_PTR>(&Windows10Lookup);
      DWORD ignored = 0;
      return VirtualProtect(&addresses->u1.Function, sizeof(addresses->u1.Function),
                            protection, &ignored) != FALSE;
    }
  }
  return false;
}

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
  if (argc != 2 && argc != 3) return Fail("expected proxy DLL path and optional test mode");
  const bool windows10 = argc == 3 && std::wstring(argv[2]) == L"--simulate-windows10";
  const bool replay = argc == 3 && std::wstring(argv[2]) == L"--appcompat-replay";
  if (argc == 3 && !windows10 && !replay) return Fail("unknown test option");
  simulate_windows10 = windows10;
  observe_appcompat = replay;

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
  if ((windows10 || replay) && !UseWindows10Lookup(proxy)) return Fail("simulated lookup setup failed");
  using SetAppCompat = void(WINAPI*)(SIZE_T, const char*);
  const auto set_appcompat = reinterpret_cast<SetAppCompat>(GetProcAddress(proxy, "SetAppCompatStringPointer"));
  const char first_compat[] = "first";
  const char last_compat[] = "last";
  if (replay) {
    if (set_appcompat == nullptr) return Fail("AppCompat export missing");
    set_appcompat(sizeof(first_compat), first_compat);
    set_appcompat(sizeof(last_compat), last_compat);
    if (appcompat_calls != 0) return Fail("AppCompat call initialized DXGI before graphics");
  }

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
  if (windows10) {
    using OptionalFn = HRESULT(WINAPI*)();
    const auto optional = reinterpret_cast<OptionalFn>(
        GetProcAddress(proxy, "DXGIDisableVBlankVirtualization"));
    if (optional == nullptr || optional() != HRESULT_FROM_WIN32(ERROR_PROC_NOT_FOUND))
      return Fail("missing optional export did not fail locally");
    if (!CallFactory(addresses[1], __uuidof(IDXGIFactory1)))
      return Fail("optional export failure poisoned factory forwarding");
  }
  if (replay) {
    if (appcompat_calls != 1 || appcompat_size != sizeof(last_compat) || appcompat_data != last_compat)
      return Fail("deferred AppCompat arguments were not replayed exactly once");
    set_appcompat(sizeof(first_compat), first_compat);
    if (appcompat_calls != 2 || appcompat_size != sizeof(first_compat) || appcompat_data != first_compat)
      return Fail("AppCompat update was not forwarded after initialization");
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
               "factories=3 system32_loaded=true recursion=false windows10="
            << (windows10 ? "true" : "false") << '\n';
  return 0;
}
