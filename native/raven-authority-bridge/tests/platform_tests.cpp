#include <windows.h>

#include <cwchar>
#include <iostream>
#include <string>

#include "hash.h"
#include "platform.h"

namespace {

int Fail(const char* message) {
  std::cerr << "FAIL: " << message << '\n';
  return 1;
}

}  // namespace

int wmain() {
  std::wstring xinput_path;
  DWORD error = ERROR_SUCCESS;
  if (!completionist::BuildSystemXInputPath(&xinput_path, &error)) {
    return Fail("BuildSystemXInputPath failed");
  }
  std::wstring system_directory = xinput_path.substr(
      0, xinput_path.find_last_of(L"\\/"));
  if (!completionist::IsPathInsideDirectory(xinput_path, system_directory)) {
    return Fail("XInput path escaped System32");
  }
  const wchar_t* basename = std::wcsrchr(xinput_path.c_str(), L'\\');
  if (basename == nullptr || _wcsicmp(basename + 1, L"XINPUT1_4.dll") != 0) {
    return Fail("XInput basename wrong");
  }
  HMODULE real_xinput = LoadLibraryExW(xinput_path.c_str(), nullptr,
                                       LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (real_xinput == nullptr) {
    return Fail("real System32 XInput did not load");
  }
  FARPROC export_address = GetProcAddress(real_xinput, "XInputGetState");
  FreeLibrary(real_xinput);
  if (export_address == nullptr) {
    return Fail("real XInput export missing");
  }
  std::wstring invalid_path;
  if (completionist::BuildSystemDllPath(L"..\\evil.dll", &invalid_path,
                                        &error)) {
    return Fail("system DLL path accepted separator");
  }
  if (completionist::IsPathInsideDirectory(L"C:\\Windows\\System32evil\\dxgi.dll",
                                            L"C:\\Windows\\System32")) {
    return Fail("directory boundary check accepted sibling prefix");
  }
  wchar_t temp_directory[MAX_PATH]{};
  wchar_t temp_path[MAX_PATH]{};
  if (GetTempPathW(MAX_PATH, temp_directory) == 0 ||
      GetTempFileNameW(temp_directory, L"cmb", 0, temp_path) == 0) {
    return Fail("temporary hash fixture path failed");
  }
  HANDLE temp_file = CreateFileW(temp_path, GENERIC_WRITE, 0, nullptr,
                                 TRUNCATE_EXISTING, FILE_ATTRIBUTE_NORMAL,
                                 nullptr);
  if (temp_file == INVALID_HANDLE_VALUE) {
    DeleteFileW(temp_path);
    return Fail("temporary hash fixture open failed");
  }
  constexpr char fixture[] = "abc";
  DWORD written = 0;
  const BOOL write_ok = WriteFile(temp_file, fixture, 3, &written, nullptr);
  CloseHandle(temp_file);
  completionist::Sha256 digest{};
  std::string hash_reason;
  const bool hash_ok = completionist::Sha256File(temp_path, &digest, &hash_reason);
  DeleteFileW(temp_path);
  if (!write_ok || written != 3 || !hash_ok ||
      completionist::Sha256Hex(digest) !=
          "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad") {
    return Fail("SHA-256 fixture mismatch");
  }
  if (completionist::IsSupportedExecutableHash(digest)) {
    return Fail("unsupported fixture hash accepted");
  }
  std::cout << "RAVEN_BRIDGE_PLATFORM_TESTS_PASSED\n";
  return 0;
}
