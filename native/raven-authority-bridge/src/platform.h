#pragma once

#include <windows.h>

#include <string>

namespace completionist {

bool BuildSystemDllPath(const wchar_t* dll_name, std::wstring* path,
                        DWORD* error);
bool BuildSystemDxgiPath(std::wstring* path, DWORD* error);
bool BuildModulePath(std::wstring* path, DWORD* error);
bool BuildModuleDirectory(std::wstring* path, DWORD* error);
bool IsPathInsideDirectory(const std::wstring& path, const std::wstring& directory);
void AppendBridgeLog(const std::string& message);

}  // namespace completionist
