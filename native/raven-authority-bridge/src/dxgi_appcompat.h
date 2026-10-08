#pragma once

#include <windows.h>

#include "dxgi_contract.generated.h"

namespace completionist {

inline constexpr unsigned int kDxgiAppCompatOrdinal = [] {
  for (const auto& item : kDxgiExports) {
    if (item.name == "SetAppCompatStringPointer") return unsigned(item.ordinal);
  }
  return 0u;
}();
static_assert(kDxgiAppCompatOrdinal != 0);

// AppCompat can invoke this export before _DllMainCRTStartup. This state must
// have constant initialization and use neither the CRT nor DLL loading. DXGI's
// setter retains the caller's pointer, so retain the same pointer until replay.
class DxgiAppCompat {
 public:
  using Setter = void(WINAPI*)(SIZE_T, const char*);

  void Set(SIZE_T size, const char* data) noexcept {
    AcquireSRWLockExclusive(&lock_);
    size_ = size;
    data_ = data;
    received_ = true;
    // The real setter only updates DXGI's compatibility state. Serialize it
    // with replay so a concurrent newer value cannot be replaced by an old one.
    if (setter_ != nullptr) setter_(size, data);
    ReleaseSRWLockExclusive(&lock_);
  }

  bool Bind(FARPROC address) noexcept {
    AcquireSRWLockExclusive(&lock_);
    setter_ = reinterpret_cast<Setter>(address);
    const bool replay = setter_ != nullptr && received_;
    if (replay) setter_(size_, data_);
    ReleaseSRWLockExclusive(&lock_);
    return replay;
  }

 private:
  SRWLOCK lock_ = SRWLOCK_INIT;
  SIZE_T size_ = 0;
  const char* data_ = nullptr;
  Setter setter_ = nullptr;
  bool received_ = false;
};

}  // namespace completionist
