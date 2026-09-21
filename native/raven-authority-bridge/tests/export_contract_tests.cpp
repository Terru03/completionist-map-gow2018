#include <windows.h>
#include <dbghelp.h>

#include <cstdint>
#include <iostream>
#include <map>
#include <string>

#include "platform.h"
#include "xinput_contract.generated.h"

namespace {

int Fail(const std::string& message) {
  std::cerr << "FAIL: " << message << '\n';
  return 1;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  if (argc != 2) return Fail("expected proxy DLL path");

  std::wstring system_path;
  DWORD path_error = ERROR_SUCCESS;
  if (!completionist::BuildSystemXInputPath(&system_path, &path_error)) {
    return Fail("system XInput path failed");
  }
  HMODULE real = LoadLibraryExW(system_path.c_str(), nullptr,
                                DONT_RESOLVE_DLL_REFERENCES);
  if (real == nullptr) return Fail("real System32 XInput map failed");
  ULONG directory_size = 0;
  auto* directory = static_cast<IMAGE_EXPORT_DIRECTORY*>(
      ImageDirectoryEntryToData(real, TRUE, IMAGE_DIRECTORY_ENTRY_EXPORT,
                                &directory_size));
  if (directory == nullptr || directory_size < sizeof(*directory)) {
    return Fail("real System32 XInput export directory missing");
  }
  const auto base = reinterpret_cast<std::uintptr_t>(real);
  const auto* functions = reinterpret_cast<const DWORD*>(
      base + directory->AddressOfFunctions);
  const auto* names =
      reinterpret_cast<const DWORD*>(base + directory->AddressOfNames);
  const auto* name_ordinals = reinterpret_cast<const WORD*>(
      base + directory->AddressOfNameOrdinals);
  std::map<std::uint16_t, std::string> real_exports;
  for (DWORD index = 0; index < directory->NumberOfFunctions; ++index) {
    if (functions[index] != 0) {
      real_exports.emplace(static_cast<std::uint16_t>(directory->Base + index),
                           std::string{});
    }
  }
  for (DWORD index = 0; index < directory->NumberOfNames; ++index) {
    const std::uint16_t ordinal = static_cast<std::uint16_t>(
        directory->Base + name_ordinals[index]);
    real_exports[ordinal] = reinterpret_cast<const char*>(base + names[index]);
  }
  if (real_exports.size() != completionist::kXInputExports.size()) {
    return Fail("pinned XInput contract count differs from System32");
  }
  for (const auto& spec : completionist::kXInputExports) {
    const auto found = real_exports.find(spec.ordinal);
    if (found == real_exports.end() || found->second != spec.name) {
      return Fail("pinned XInput name/ordinal differs from System32");
    }
  }

  HMODULE proxy = LoadLibraryExW(argv[1], nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
  if (proxy == nullptr) return Fail("proxy DLL did not load");
  for (const auto& [ordinal, name] : real_exports) {
    FARPROC by_ordinal =
        GetProcAddress(proxy, MAKEINTRESOURCEA(static_cast<WORD>(ordinal)));
    if (by_ordinal == nullptr) {
      return Fail("proxy misses System32 export ordinal " +
                  std::to_string(ordinal));
    }
    if (!name.empty()) {
      FARPROC by_name = GetProcAddress(proxy, name.c_str());
      if (by_name == nullptr || by_name != by_ordinal) {
        return Fail("proxy name/ordinal alias mismatch for " + name);
      }
    }
  }
  FARPROC snapshot = GetProcAddress(proxy, "CompletionistMapGetRavenSnapshotV1");
  if (snapshot == nullptr ||
      snapshot != GetProcAddress(proxy, MAKEINTRESOURCEA(
                                           completionist::kSnapshotExportOrdinal))) {
    return Fail("snapshot API name/ordinal mismatch");
  }
  const DWORD named_count = directory->NumberOfNames;
  FreeLibrary(proxy);
  FreeLibrary(real);
  std::cout << "RAVEN_BRIDGE_EXPORT_CONTRACT_TEST_PASSED system_exports="
            << real_exports.size() << " named=" << named_count
            << " ordinal_only="
            << (real_exports.size() - named_count) << '\n';
  return 0;
}
