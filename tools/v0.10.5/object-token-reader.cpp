#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

struct TValue {
  std::uint64_t value;
  std::uint32_t tag;
  std::uint32_t padding;
};

using PushString = void(__fastcall*)(void* state, const char* value);

constexpr std::uintptr_t kPushStringRva = 0x9E4360;
constexpr std::uint32_t kEngineObjectTag = 2;

const unsigned char kPushStringPrefix[] = {
    0x48, 0x89, 0x5C, 0x24, 0x08, 0x57, 0x48, 0x83, 0xEC, 0x20,
};
const unsigned char kObjectTValueWrite[] = {
    0x48, 0x89, 0x18, 0xC7, 0x40, 0x08, 0x02, 0x00, 0x00, 0x00,
};
const unsigned char kFirstArgumentLayout[] = {
    0x48, 0x8B, 0x41, 0x20, 0x48, 0x8B, 0x10, 0x48, 0x83, 0xC2, 0x10,
};

std::uintptr_t image_base() {
  return reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
}

bool bytes_equal(std::uintptr_t address, const unsigned char* expected, std::size_t size) {
  return std::memcmp(reinterpret_cast<const void*>(address), expected, size) == 0;
}

bool supported_binary() {
  const auto base = image_base();
  return base != 0 &&
         bytes_equal(base + kPushStringRva, kPushStringPrefix, sizeof(kPushStringPrefix)) &&
         bytes_equal(base + 0x547AE2, kObjectTValueWrite, sizeof(kObjectTValueWrite)) &&
         bytes_equal(base + 0x5AA21E, kFirstArgumentLayout, sizeof(kFirstArgumentLayout));
}

TValue* stack_top(void* state) {
  if (state == nullptr) return nullptr;
  return *reinterpret_cast<TValue**>(reinterpret_cast<std::uintptr_t>(state) + 0x10);
}

TValue* function_slot(void* state) {
  if (state == nullptr) return nullptr;
  const auto raw = reinterpret_cast<std::uintptr_t>(state);
  const auto call_info = *reinterpret_cast<std::uintptr_t*>(raw + 0x20);
  if (call_info == 0) return nullptr;
  return *reinterpret_cast<TValue**>(call_info);
}

TValue* first_argument(void* state) {
  auto* top = stack_top(state);
  auto* fn = function_slot(state);
  if (top == nullptr || fn == nullptr || fn + 1 >= top) return nullptr;
  return fn + 1;
}

int read_object_token(void* state) {
  const TValue* argument = first_argument(state);
  if (argument == nullptr || (argument->tag & 0xF) != kEngineObjectTag ||
      (argument->value & 1) == 0) {
    return 0;
  }
  char text[32]{};
  ::sprintf_s(text, sizeof(text), "0x%016llx",
              static_cast<unsigned long long>(argument->value));
  const auto push_string = reinterpret_cast<PushString>(image_base() + kPushStringRva);
  push_string(state, text);
  return 1;
}

int return_self(void* state) {
  auto* top = stack_top(state);
  const auto* fn = function_slot(state);
  if (top == nullptr || fn == nullptr) return 0;
  *top = *fn;
  *reinterpret_cast<TValue**>(reinterpret_cast<std::uintptr_t>(state) + 0x10) = top + 1;
  return 1;
}

}  // namespace

extern "C" __declspec(dllexport) int luaopen_completionist_object_token(void* state) {
  if (!supported_binary() || state == nullptr) return 0;

  // package.loadlib returns this exported function.  The probe calls it once
  // with no arguments to obtain a reusable reader function.  Reuse the exact
  // function TValue Lua already created rather than manufacturing a C-function
  // TValue ourselves.  This avoids depending on an inferred function tag.
  if (first_argument(state) == nullptr) return return_self(state);

  return read_object_token(state);
}
