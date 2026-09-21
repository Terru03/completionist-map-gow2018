#include "hash.h"

#include <windows.h>
#include <bcrypt.h>

#include <array>
#include <vector>

namespace completionist {
namespace {

constexpr char kSupportedExeSha256[] =
    "caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452";

bool NtSuccess(NTSTATUS status) { return status >= 0; }

}  // namespace

bool Sha256File(const std::wstring& path, Sha256* digest, std::string* reason) {
  if (digest == nullptr) {
    if (reason != nullptr) {
      *reason = "null_digest";
    }
    return false;
  }
  HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ,
                            nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL,
                            nullptr);
  if (file == INVALID_HANDLE_VALUE) {
    if (reason != nullptr) {
      *reason = "open_failed:" + std::to_string(GetLastError());
    }
    return false;
  }
  BCRYPT_ALG_HANDLE algorithm = nullptr;
  BCRYPT_HASH_HANDLE hash = nullptr;
  std::vector<std::uint8_t> object;
  bool ok = false;
  do {
    if (!NtSuccess(BCryptOpenAlgorithmProvider(
            &algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0))) {
      if (reason != nullptr) *reason = "bcrypt_open_failed";
      break;
    }
    DWORD object_length = 0;
    DWORD result_length = 0;
    if (!NtSuccess(BCryptGetProperty(
            algorithm, BCRYPT_OBJECT_LENGTH,
            reinterpret_cast<PUCHAR>(&object_length), sizeof(object_length),
            &result_length, 0)) || object_length == 0) {
      if (reason != nullptr) *reason = "bcrypt_object_length_failed";
      break;
    }
    object.resize(object_length);
    if (!NtSuccess(BCryptCreateHash(algorithm, &hash, object.data(),
                                    object_length, nullptr, 0, 0))) {
      if (reason != nullptr) *reason = "bcrypt_create_failed";
      break;
    }
    std::vector<std::uint8_t> buffer(1024 * 1024);
    for (;;) {
      DWORD read = 0;
      if (!ReadFile(file, buffer.data(), static_cast<DWORD>(buffer.size()),
                    &read, nullptr)) {
        if (reason != nullptr) {
          *reason = "read_failed:" + std::to_string(GetLastError());
        }
        break;
      }
      if (read == 0) {
        if (!NtSuccess(BCryptFinishHash(hash, digest->data(),
                                        static_cast<ULONG>(digest->size()),
                                        0))) {
          if (reason != nullptr) *reason = "bcrypt_finish_failed";
        } else {
          ok = true;
        }
        break;
      }
      if (!NtSuccess(BCryptHashData(hash, buffer.data(), read, 0))) {
        if (reason != nullptr) *reason = "bcrypt_update_failed";
        break;
      }
    }
  } while (false);
  if (hash != nullptr) BCryptDestroyHash(hash);
  if (algorithm != nullptr) BCryptCloseAlgorithmProvider(algorithm, 0);
  CloseHandle(file);
  return ok;
}

std::string Sha256Hex(const Sha256& digest) {
  constexpr char digits[] = "0123456789abcdef";
  std::string output;
  output.reserve(64);
  for (const std::uint8_t value : digest) {
    output.push_back(digits[value >> 4]);
    output.push_back(digits[value & 0x0f]);
  }
  return output;
}

bool IsSupportedExecutableHash(const Sha256& digest) {
  return Sha256Hex(digest) == kSupportedExeSha256;
}

}  // namespace completionist
