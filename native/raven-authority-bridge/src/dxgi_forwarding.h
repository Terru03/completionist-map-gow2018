#pragma once

#include <windows.h>
#include <array>
#include <string>

#include "dxgi_contract.generated.h"
#include "platform.h"

namespace completionist {

inline bool ResolveDxgiExportsByName(
    HMODULE module, std::array<FARPROC, kDxgiExports.size()>* output,
    DWORD* error) {
  std::array<FARPROC, kDxgiExports.size()> resolved{};
  for (std::size_t index = 0; index < kDxgiExports.size(); ++index) {
    const std::string name(kDxgiExports[index].name);
    resolved[index] = GetProcAddress(module, name.c_str());
    if (resolved[index] != nullptr) continue;
    if (name == "CreateDXGIFactory" || name == "CreateDXGIFactory1" ||
        name == "CreateDXGIFactory2") {
      *error = ERROR_PROC_NOT_FOUND;
      AppendBridgeLog("DXGI_FORWARDING_REJECTED missing_factory=" + name);
      return false;
    }
    // Windows 10 lacks some exports. Keep working factories live.
    AppendBridgeLog("DXGI_OPTIONAL_EXPORT_UNAVAILABLE name=" + name);
  }
  *output = resolved;
  *error = ERROR_SUCCESS;
  return true;
}

}  // namespace completionist
