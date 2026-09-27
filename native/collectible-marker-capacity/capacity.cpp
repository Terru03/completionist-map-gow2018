#include "capacity.h"
#include <algorithm>
#include <cstring>
#include <limits>

namespace collectible {
bool MakeConstructorPatch(std::span<const std::uint8_t> original,
                          std::uintptr_t code_address, std::uintptr_t storage,
                          Code* patched) {
  constexpr std::array<std::uint8_t, 18> expected{
    0x48,0x8d,0x0d,0xa9,0x3f,0x5e,0x02,
    0x48,0xc7,0x05,0x7e,0x3f,0x5e,0x02,0xdb,0x02,0x00,0x00};
  constexpr std::array<std::uint8_t, 5> clear_count{0xb8,0xdc,0x02,0x00,0x00};
  if (patched == nullptr || original.size() != kConstructorBytes ||
      !std::equal(expected.begin(), expected.end(), original.begin()) ||
      !std::equal(clear_count.begin(), clear_count.end(), original.begin()+0x5b)) return false;
  const auto delta = static_cast<std::int64_t>(storage) -
                     static_cast<std::int64_t>(code_address + 7);
  if (delta < (std::numeric_limits<std::int32_t>::min)() ||
      delta > (std::numeric_limits<std::int32_t>::max)()) return false;
  std::copy(original.begin(), original.end(), patched->begin());
  const auto displacement = static_cast<std::int32_t>(delta);
  const std::uint32_t last = kSlots-1, count = kSlots;
  std::memcpy(patched->data()+3, &displacement, 4);
  std::memcpy(patched->data()+14, &last, 4);
  std::memcpy(patched->data()+0x5c, &count, 4);
  return true;
}

bool IsEmptyNativeRegistry(const Registry& registry, std::uintptr_t address) {
  if (registry.count != 0 || registry.zero_key_present != 0) return false;
  return (registry.last_slot == 0 && registry.slots == nullptr) ||
         (registry.last_slot == kNativeSlots-1 &&
          reinterpret_cast<std::uintptr_t>(registry.slots) == address+sizeof(Registry));
}

bool MakeEntityReferencePatch(const Reference& original, std::size_t index,
                             std::uintptr_t base, std::uintptr_t storage,
                             Reference* patched) {
  constexpr std::array<std::array<std::uint8_t, 3>, 7> opcodes{{
      {0x48,0x8d,0x05}, {0x48,0x8d,0x05}, {0x4c,0x8d,0x35},
      {0x4c,0x8d,0x35}, {0x48,0x8d,0x0d}, {0x4c,0x8d,0x35}, {0x48,0x8d,0x35}}};
  if (patched == nullptr || index >= kEntityReferences.size() ||
      !std::equal(opcodes[index].begin(), opcodes[index].end(), original.begin())) return false;
  std::int32_t old_delta = 0;
  std::memcpy(&old_delta, original.data()+3, 4);
  const auto next = base+kEntityReferences[index]+original.size();
  if (next+old_delta != base+kEntityArrayRva) return false;
  const auto delta = static_cast<std::int64_t>(storage)-static_cast<std::int64_t>(next);
  if (delta < (std::numeric_limits<std::int32_t>::min)() ||
      delta > (std::numeric_limits<std::int32_t>::max)()) return false;
  *patched = original;
  const auto value = static_cast<std::int32_t>(delta);
  std::memcpy(patched->data()+3, &value, 4);
  return true;
}

bool MakeUiPhysicsPatch(const PhysicsCall& original, std::uintptr_t base,
                        std::uintptr_t storage, PhysicsCall* patched,
                        PhysicsThunk* thunk) {
  constexpr PhysicsCall expected{0xe8,0xfd,0x73,0x0a,0x00};
  if (patched == nullptr || thunk == nullptr || original != expected) return false;
  const auto delta = static_cast<std::int64_t>(storage) -
                     static_cast<std::int64_t>(base+kPhysicsSizeCallRva+5);
  if (delta < (std::numeric_limits<std::int32_t>::min)() ||
      delta > (std::numeric_limits<std::int32_t>::max)()) return false;
  // At this call site ESI is the physics-world index, and RCX points to the
  // constructor parameters. World 7 is the UI collision world, whose two
  // capacities otherwise fall back to 500. Adjust them BEFORE the engine
  // computes and allocates the backing memory for all dependent pools.
  PhysicsThunk code{
    0x83,0xfe,0x07,                         // cmp esi, 7
    0x75,0x0e,                              // jne original_size_function
    0xc7,0x41,0x14,0,0,0,0,                 // mov [rcx+14h], rigid_body_count
    0xc7,0x41,0x1c,0,0,0,0,                 // mov [rcx+1ch], shape_count
    0xff,0x25,0,0,0,0,                      // jmp [rip] (no register/stack changes)
    0,0,0,0,0,0,0,0};
  const auto target = base+kPhysicsSizeRva;
  std::memcpy(code.data()+8, &kUiPhysicsSlots, 4);
  std::memcpy(code.data()+15, &kUiPhysicsSlots, 4);
  std::memcpy(code.data()+25, &target, 8);
  *patched = original;
  const auto displacement = static_cast<std::int32_t>(delta);
  std::memcpy(patched->data()+1, &displacement, 4);
  *thunk = code;
  return true;
}
}
