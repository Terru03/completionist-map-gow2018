#include <windows.h>
#include <dbghelp.h>

#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <string>

#include "dxgi_contract.generated.h"
#include "platform.h"

namespace {

struct ExportEntry {
  std::string name;
  std::string forwarder;
};

int Fail(const std::string& message) {
  std::cerr << "FAIL: " << message << '\n';
  return 1;
}

bool ReadExports(const std::wstring& path,
                 std::map<std::uint16_t, ExportEntry>* exports,
                 std::string* reason) {
  HMODULE module =
      LoadLibraryExW(path.c_str(), nullptr, DONT_RESOLVE_DLL_REFERENCES);
  if (module == nullptr) {
    *reason = "PE image did not map";
    return false;
  }
  ULONG directory_size = 0;
  auto* directory = static_cast<IMAGE_EXPORT_DIRECTORY*>(
      ImageDirectoryEntryToData(module, TRUE, IMAGE_DIRECTORY_ENTRY_EXPORT,
                                &directory_size));
  const auto* nt = ImageNtHeader(module);
  if (directory == nullptr || directory_size < sizeof(*directory) ||
      nt == nullptr) {
    FreeLibrary(module);
    *reason = "export directory missing";
    return false;
  }
  const auto base = reinterpret_cast<std::uintptr_t>(module);
  const auto* functions =
      reinterpret_cast<const DWORD*>(base + directory->AddressOfFunctions);
  const auto* names =
      reinterpret_cast<const DWORD*>(base + directory->AddressOfNames);
  const auto* name_ordinals =
      reinterpret_cast<const WORD*>(base + directory->AddressOfNameOrdinals);
  const DWORD export_rva =
      nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT]
          .VirtualAddress;
  const DWORD export_size =
      nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT].Size;
  exports->clear();
  for (DWORD index = 0; index < directory->NumberOfFunctions; ++index) {
    const DWORD function_rva = functions[index];
    if (function_rva == 0) continue;
    ExportEntry entry;
    if (function_rva >= export_rva && function_rva - export_rva < export_size) {
      entry.forwarder = reinterpret_cast<const char*>(base + function_rva);
    }
    exports->emplace(static_cast<std::uint16_t>(directory->Base + index),
                     std::move(entry));
  }
  std::set<std::string> unique_names;
  for (DWORD index = 0; index < directory->NumberOfNames; ++index) {
    const std::uint16_t ordinal = static_cast<std::uint16_t>(
        directory->Base + name_ordinals[index]);
    const std::string name =
        reinterpret_cast<const char*>(base + names[index]);
    const auto found = exports->find(ordinal);
    if (found == exports->end() || !found->second.name.empty() ||
        !unique_names.insert(name).second) {
      FreeLibrary(module);
      *reason = "export name collision";
      return false;
    }
    found->second.name = name;
  }
  FreeLibrary(module);
  return true;
}

bool ValidateSystemContract(const std::map<std::uint16_t, ExportEntry>& real,
                            std::string* reason) {
  for (const char* name : {"CreateDXGIFactory", "CreateDXGIFactory1", "CreateDXGIFactory2"}) {
    bool found = false;
    for (const auto& [ordinal, entry] : real) {
      (void)ordinal;
      found = found || entry.name == name;
    }
    if (!found) {
      *reason = std::string("System32 DXGI factory missing: ") + name;
      return false;
    }
  }
  return true;
}

bool ValidateProxyContract(const std::map<std::uint16_t, ExportEntry>& proxy,
                           std::string* reason) {
  if (proxy.size() != completionist::kDxgiExports.size() + 1) {
    *reason = "proxy export count is not complete contract plus snapshot API";
    return false;
  }
  for (const auto& spec : completionist::kDxgiExports) {
    const auto found = proxy.find(spec.ordinal);
    if (found == proxy.end() || found->second.name != spec.name) {
      *reason = "proxy misses or changes DXGI name/ordinal";
      return false;
    }
  }
  const auto snapshot = proxy.find(completionist::kSnapshotExportOrdinal);
  if (snapshot == proxy.end() ||
      snapshot->second.name != "CompletionistMapGetRavenSnapshotV1") {
    *reason = "snapshot API name/ordinal mismatch";
    return false;
  }
  const auto factory2 = proxy.find(12);
  if (factory2 == proxy.end() || factory2->second.name != "CreateDXGIFactory2") {
    *reason = "proxy misses CreateDXGIFactory2 ordinal 12";
    return false;
  }
  return true;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  if (argc != 2 && argc != 3) return Fail("expected proxy DLL path");
  const bool expect_rejected =
      argc == 3 && std::wstring(argv[2]) == L"--expect-rejected";

  std::wstring system_path;
  DWORD path_error = ERROR_SUCCESS;
  if (!completionist::BuildSystemDxgiPath(&system_path, &path_error)) {
    return Fail("System32 DXGI path failed");
  }
  std::map<std::uint16_t, ExportEntry> real_exports;
  std::string reason;
  if (!ReadExports(system_path, &real_exports, &reason) ||
      !ValidateSystemContract(real_exports, &reason)) {
    return Fail(reason);
  }

  std::map<std::uint16_t, ExportEntry> proxy_exports;
  const bool proxy_valid = ReadExports(argv[1], &proxy_exports, &reason) &&
                           ValidateProxyContract(proxy_exports, &reason);
  if (expect_rejected) {
    if (proxy_valid) return Fail("incomplete DXGI proxy was accepted");
    std::cout << "RAVEN_BRIDGE_INCOMPLETE_DXGI_REJECTED reason=" << reason
              << '\n';
    return 0;
  }
  if (!proxy_valid) return Fail(reason);

  HMODULE proxy =
      LoadLibraryExW(argv[1], nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
  if (proxy == nullptr) return Fail("proxy DLL did not load");
  for (const auto& spec : completionist::kDxgiExports) {
    FARPROC by_ordinal = GetProcAddress(
        proxy, MAKEINTRESOURCEA(static_cast<WORD>(spec.ordinal)));
    const std::string name(spec.name);
    FARPROC by_name = GetProcAddress(proxy, name.c_str());
    if (by_ordinal == nullptr || by_name == nullptr || by_name != by_ordinal) {
      return Fail("runtime proxy name/ordinal mismatch for " + name);
    }
  }
  FARPROC snapshot = GetProcAddress(proxy, "CompletionistMapGetRavenSnapshotV1");
  if (snapshot == nullptr ||
      snapshot != GetProcAddress(proxy, MAKEINTRESOURCEA(
                                          completionist::kSnapshotExportOrdinal))) {
    return Fail("runtime snapshot API name/ordinal mismatch");
  }
  FreeLibrary(proxy);
  std::cout << "RAVEN_BRIDGE_EXPORT_CONTRACT_TEST_PASSED system_exports="
            << real_exports.size() << " proxy_named=20 proxy_ordinal_only=0 "
               "create_dxgi_factory2=true\n";
  return 0;
}
