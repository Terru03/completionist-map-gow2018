#include "platform.h"

#include <algorithm>
#include <array>
#include <cwchar>
#include <cwctype>
#include <cstdio>
#include <string_view>

namespace completionist {
namespace {

constexpr wchar_t kLogRelativePath[] =
    L"mods\\completionist-map\\native\\raven-native-bridge.log";

bool AddPathPart(std::wstring* path, std::wstring_view part) {
  if (path == nullptr || path->empty() || part.empty()) {
    return false;
  }
  if (path->back() != L'\\') {
    path->push_back(L'\\');
  }
  path->append(part);
  return true;
}

bool GetModulePathInternal(std::wstring* path, DWORD* error) {
  if (path == nullptr) {
    if (error != nullptr) {
      *error = ERROR_INVALID_PARAMETER;
    }
    return false;
  }
  std::array<wchar_t, 32768> buffer{};
  const DWORD length = GetModuleFileNameW(nullptr, buffer.data(),
                                          static_cast<DWORD>(buffer.size()));
  if (length == 0 || length >= buffer.size()) {
    if (error != nullptr) {
      *error = length == 0 ? GetLastError() : ERROR_INSUFFICIENT_BUFFER;
    }
    return false;
  }
  path->assign(buffer.data(), length);
  return true;
}

std::wstring Lower(std::wstring value) {
  std::transform(value.begin(), value.end(), value.begin(),
                 [](wchar_t ch) { return static_cast<wchar_t>(towlower(ch)); });
  return value;
}

void EnsureLogDirectories(const std::wstring& root) {
  std::wstring current = root;
  for (const wchar_t* part : {L"mods", L"completionist-map", L"native"}) {
    if (!AddPathPart(&current, part)) {
      return;
    }
    if (!CreateDirectoryW(current.c_str(), nullptr) &&
        GetLastError() != ERROR_ALREADY_EXISTS) {
      return;
    }
  }
}

}  // namespace

bool BuildSystemDllPath(const wchar_t* dll_name, std::wstring* path,
                        DWORD* error) {
  if (dll_name == nullptr || dll_name[0] == L'\0' || path == nullptr ||
      std::wcschr(dll_name, L'\\') != nullptr ||
      std::wcschr(dll_name, L'/') != nullptr) {
    if (error != nullptr) {
      *error = ERROR_INVALID_PARAMETER;
    }
    return false;
  }
  std::array<wchar_t, 32768> buffer{};
  const UINT length = GetSystemDirectoryW(buffer.data(),
                                          static_cast<UINT>(buffer.size()));
  if (length == 0 || length >= buffer.size()) {
    if (error != nullptr) {
      *error = length == 0 ? GetLastError() : ERROR_INSUFFICIENT_BUFFER;
    }
    return false;
  }
  path->assign(buffer.data(), length);
  if (!AddPathPart(path, dll_name)) {
    if (error != nullptr) {
      *error = ERROR_INVALID_NAME;
    }
    return false;
  }
  if (error != nullptr) {
    *error = ERROR_SUCCESS;
  }
  return true;
}

bool BuildSystemDxgiPath(std::wstring* path, DWORD* error) {
  return BuildSystemDllPath(L"dxgi.dll", path, error);
}

bool BuildModulePath(std::wstring* path, DWORD* error) {
  return GetModulePathInternal(path, error);
}

bool BuildModuleDirectory(std::wstring* path, DWORD* error) {
  if (!GetModulePathInternal(path, error)) {
    return false;
  }
  const size_t slash = path->find_last_of(L"\\/");
  if (slash == std::wstring::npos) {
    if (error != nullptr) {
      *error = ERROR_INVALID_NAME;
    }
    return false;
  }
  path->resize(slash);
  return true;
}

bool IsPathInsideDirectory(const std::wstring& path,
                           const std::wstring& directory) {
  if (path.empty() || directory.empty()) {
    return false;
  }
  std::wstring normalized_path = Lower(path);
  std::wstring normalized_directory = Lower(directory);
  while (!normalized_directory.empty() &&
         (normalized_directory.back() == L'\\' ||
          normalized_directory.back() == L'/')) {
    normalized_directory.pop_back();
  }
  if (normalized_path.size() <= normalized_directory.size() ||
      normalized_path.compare(0, normalized_directory.size(),
                              normalized_directory) != 0) {
    return false;
  }
  const wchar_t boundary = normalized_path[normalized_directory.size()];
  return boundary == L'\\' || boundary == L'/';
}

void AppendBridgeLog(const std::string& message) {
  std::wstring root;
  DWORD error = ERROR_SUCCESS;
  if (!BuildModuleDirectory(&root, &error)) {
    return;
  }
  EnsureLogDirectories(root);
  std::wstring path = root;
  if (!AddPathPart(&path, kLogRelativePath)) {
    return;
  }
  HANDLE file = CreateFileW(path.c_str(), FILE_APPEND_DATA,
                            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                            OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file == INVALID_HANDLE_VALUE) {
    return;
  }
  SYSTEMTIME now{};
  GetSystemTime(&now);
  char prefix[64]{};
  const int prefix_length = std::snprintf(
      prefix, sizeof(prefix), "%04u-%02u-%02uT%02u:%02u:%02u.%03uZ ",
      now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute, now.wSecond,
      now.wMilliseconds);
  std::string line;
  if (prefix_length > 0) {
    line.assign(prefix, static_cast<size_t>(prefix_length));
  }
  line += message;
  line += "\r\n";
  DWORD written = 0;
  WriteFile(file, line.data(), static_cast<DWORD>(line.size()), &written,
            nullptr);
  CloseHandle(file);
}

}  // namespace completionist
