#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace collectible {
inline constexpr std::size_t kNativeSlots = 732;
inline constexpr std::size_t kSlots = 2048;
inline constexpr std::uintptr_t kConstructorRva = 0x6c2298;
inline constexpr std::uintptr_t kRegistryRva = 0x2ca6220;
inline constexpr std::size_t kConstructorBytes = 0x75;
inline constexpr std::uintptr_t kEntityArrayRva = 0x22c3d00;
inline constexpr std::uintptr_t kEntityCountRva = 0x22c3cfc;
inline constexpr std::size_t kEntitySlots = 4096;
inline constexpr std::uint32_t kUiPhysicsSlots = 2048;
inline constexpr std::uintptr_t kPhysicsSizeCallRva = 0x543e4e;
inline constexpr std::uintptr_t kPhysicsSizeRva = 0x5eb250;
using PhysicsCall = std::array<std::uint8_t, 5>;
using PhysicsThunk = std::array<std::uint8_t, 33>;
inline constexpr std::array<std::uintptr_t, 7> kEntityReferences{
    0x6196fe, 0x61a045, 0x61a9e2, 0x61b0ed, 0x61b373, 0x61bd26, 0x61c560};
using Reference = std::array<std::uint8_t, 7>;
struct Slot { std::uint64_t id; std::uint64_t value; };
struct Registry {
  std::uint64_t count;
  std::uint64_t last_slot;
  std::uint64_t zero_key_present;
  Slot* slots;
  std::uint64_t zero_key_value;
};
static_assert(sizeof(Slot) == 16 && sizeof(Registry) == 40);
using Code = std::array<std::uint8_t, kConstructorBytes>;
bool MakeConstructorPatch(std::span<const std::uint8_t> original,
                          std::uintptr_t code_address, std::uintptr_t storage,
                          Code* patched);
bool IsEmptyNativeRegistry(const Registry& registry, std::uintptr_t address);
bool MakeEntityReferencePatch(const Reference& original, std::size_t index,
                             std::uintptr_t base, std::uintptr_t storage,
                             Reference* patched);
bool MakeUiPhysicsPatch(const PhysicsCall& original, std::uintptr_t base,
                        std::uintptr_t storage, PhysicsCall* patched,
                        PhysicsThunk* thunk);
}
