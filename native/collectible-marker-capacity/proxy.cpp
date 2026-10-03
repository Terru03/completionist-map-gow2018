#include <windows.h>
#include <array>
#include <cstring>
#include <string>
#include "capacity.h"
#include "dxgi_contract.generated.h"
#include "dxgi_forwarding.h"
#include "hash.h"
#include "platform.h"

namespace {
INIT_ONCE once = INIT_ONCE_STATIC_INIT;
std::array<FARPROC, completionist::kDxgiExports.size()> exports{};
FARPROC snapshot = nullptr;
DWORD failure = ERROR_DLL_INIT_FAILED;
// Retained for process lifetime: the engine owns references to this storage.
void* marker_storage = nullptr;
void* entity_storage = nullptr;
void* physics_thunk = nullptr;
#ifndef COLLECTIBLE_UPSTREAM_SHA256
#define COLLECTIBLE_UPSTREAM_SHA256 "cc91a2ea4475c83085488c33bb0ece223f958054c1a4ac71d26d67a31a84f7b7"
#endif
constexpr char kUpstreamHash[] = COLLECTIBLE_UPSTREAM_SHA256;

void* AllocateNear(std::uintptr_t base, std::size_t bytes) {
  constexpr std::uintptr_t granularity = 0x10000;
  auto address = (base + 0x5200000 + granularity-1) & ~(granularity-1);
  const auto end = base + 0x70000000;
  while (address < end) {
    MEMORY_BASIC_INFORMATION info{};
    if (!VirtualQuery(reinterpret_cast<void*>(address), &info, sizeof(info))) break;
    const auto next = reinterpret_cast<std::uintptr_t>(info.BaseAddress) + info.RegionSize;
    if (info.State == MEM_FREE && next-address >= bytes) {
      void* storage = VirtualAlloc(reinterpret_cast<void*>(address),
          bytes, MEM_RESERVE|MEM_COMMIT, PAGE_READWRITE);
      if (storage != nullptr) return storage;
    }
    address = (next+granularity-1) & ~(granularity-1);
  }
  return nullptr;
}

bool ExpandCapacity(std::uintptr_t base) {
  auto* registry = reinterpret_cast<collectible::Registry*>(base+collectible::kRegistryRva);
  if (!collectible::IsEmptyNativeRegistry(*registry, reinterpret_cast<std::uintptr_t>(registry))) {
    completionist::AppendBridgeLog("COLLECTIBLE_CAPACITY_REJECTED reason=registry_already_used_or_unknown");
    return false;
  }
  void* storage = AllocateNear(base, collectible::kSlots*sizeof(collectible::Slot));
  if (storage == nullptr) return false;
  auto* code = reinterpret_cast<std::uint8_t*>(base+collectible::kConstructorRva);
  collectible::Code original{}, patched{};
  std::memcpy(original.data(), code, original.size());
  if (!collectible::MakeConstructorPatch(original, reinterpret_cast<std::uintptr_t>(code),
                                        reinterpret_cast<std::uintptr_t>(storage), &patched)) {
    VirtualFree(storage, 0, MEM_RELEASE);
    return false;
  }
  DWORD old_protection = 0;
  if (!VirtualProtect(code, patched.size(), PAGE_EXECUTE_READWRITE, &old_protection)) {
    VirtualFree(storage, 0, MEM_RELEASE);
    return false;
  }
  std::memcpy(code, patched.data(), patched.size());
  const BOOL flushed = FlushInstructionCache(GetCurrentProcess(), code, patched.size());
  DWORD ignored = 0;
  const BOOL protected_again = VirtualProtect(code, patched.size(), old_protection, &ignored);
  if (!flushed || !protected_again) {
    DWORD restore_protection = 0;
    if (VirtualProtect(code, original.size(), PAGE_EXECUTE_READWRITE, &restore_protection)) {
      std::memcpy(code, original.data(), original.size());
      FlushInstructionCache(GetCurrentProcess(), code, original.size());
      VirtualProtect(code, original.size(), old_protection, &ignored);
    }
    // Keep the allocation alive even if restoring protection failed.
    return false;
  }
  marker_storage = storage;
  // The first DXGI export runs before map ingestion. If the constructor has
  // already run, update its still-empty header too. Later constructor calls
  // use the patched pointer and both patched clear-loop bounds.
  registry->slots = static_cast<collectible::Slot*>(storage);
  registry->last_slot = collectible::kSlots-1;
  completionist::AppendBridgeLog(
      "COLLECTIBLE_CAPACITY_READY native_slots=732 slots=2048 exe_disk_unchanged=true");
  return true;
}

bool ExpandEntityArray(std::uintptr_t base) {
  // The map's collision query collects both world objects and icon objects.
  // Its unchecked 512-pointer array overflows before the first map frame at
  // 653 entries in the reproduced crash. All seven references are redirected;
  // the existing count and world-object lifecycle remain owned by the engine.
  if (*reinterpret_cast<const std::uint32_t*>(base+collectible::kEntityCountRva) != 0) {
    completionist::AppendBridgeLog("COLLECTIBLE_ENTITY_CAPACITY_REJECTED reason=array_already_used");
    return false;
  }
  void* storage = AllocateNear(base, collectible::kEntitySlots*sizeof(void*));
  if (storage == nullptr) return false;
  std::array<collectible::Reference, collectible::kEntityReferences.size()> originals{}, patches{};
  for (std::size_t i=0; i<patches.size(); ++i) {
    std::memcpy(originals[i].data(), reinterpret_cast<void*>(base+collectible::kEntityReferences[i]), 7);
    if (!collectible::MakeEntityReferencePatch(originals[i], i, base,
                                             reinterpret_cast<std::uintptr_t>(storage), &patches[i])) {
      VirtualFree(storage, 0, MEM_RELEASE);
      completionist::AppendBridgeLog("COLLECTIBLE_ENTITY_CAPACITY_REJECTED reason=instruction_layout");
      return false;
    }
  }
  // Preflight all pages before changing any operand. At this initialization
  // boundary no level or map query has populated the array yet.
  std::array<DWORD, collectible::kEntityReferences.size()> protections{};
  std::size_t writable = 0;
  for (; writable<patches.size(); ++writable) {
    if (!VirtualProtect(reinterpret_cast<void*>(base+collectible::kEntityReferences[writable]),
                        7, PAGE_EXECUTE_READWRITE, &protections[writable])) break;
  }
  if (writable != patches.size()) {
    while (writable>0) {
      --writable;
      DWORD ignored;
      VirtualProtect(reinterpret_cast<void*>(base+collectible::kEntityReferences[writable]),
                     7, protections[writable], &ignored);
    }
    VirtualFree(storage, 0, MEM_RELEASE);
    return false;
  }
  entity_storage = storage;
  for (std::size_t i=0; i<patches.size(); ++i)
    std::memcpy(reinterpret_cast<void*>(base+collectible::kEntityReferences[i]+3), patches[i].data()+3, 4);
  bool ok = FlushInstructionCache(GetCurrentProcess(), nullptr, 0) != FALSE;
  // Reverse order also restores shared pages to their original protection.
  for (std::size_t i=patches.size(); i>0; --i) {
    DWORD ignored;
    ok = (VirtualProtect(reinterpret_cast<void*>(base+collectible::kEntityReferences[i-1]),
                         7, protections[i-1], &ignored) != FALSE) && ok;
  }
  if (ok) completionist::AppendBridgeLog("COLLECTIBLE_ENTITY_CAPACITY_READY native_slots=512 slots=4096 references=7");
  return ok;
}

bool ExpandUiPhysics(std::uintptr_t base) {
  // World creation must not have happened yet. Changing the parameters at the
  // size-calculation call lets the engine own allocation and pool lifecycle.
  const auto* worlds = reinterpret_cast<const std::uintptr_t*>(base+0x22ae7e0);
  for (std::size_t i=0; i<8; ++i) {
    if (worlds[i] != 0) {
      completionist::AppendBridgeLog("COLLECTIBLE_UI_PHYSICS_REJECTED reason=world_already_created");
      return false;
    }
  }
  void* storage = AllocateNear(base, sizeof(collectible::PhysicsThunk));
  if (storage == nullptr) return false;
  auto* call = reinterpret_cast<void*>(base+collectible::kPhysicsSizeCallRva);
  collectible::PhysicsCall original{}, patched{};
  collectible::PhysicsThunk thunk{};
  std::memcpy(original.data(), call, original.size());
  if (!collectible::MakeUiPhysicsPatch(original, base,
                                     reinterpret_cast<std::uintptr_t>(storage), &patched, &thunk)) {
    VirtualFree(storage, 0, MEM_RELEASE);
    completionist::AppendBridgeLog("COLLECTIBLE_UI_PHYSICS_REJECTED reason=instruction_layout");
    return false;
  }
  std::memcpy(storage, thunk.data(), thunk.size());
  DWORD old_protection = 0;
  if (!VirtualProtect(storage, thunk.size(), PAGE_EXECUTE_READ, &old_protection) ||
      !FlushInstructionCache(GetCurrentProcess(), storage, thunk.size()) ||
      !VirtualProtect(call, patched.size(), PAGE_EXECUTE_READWRITE, &old_protection)) {
    VirtualFree(storage, 0, MEM_RELEASE);
    return false;
  }
  // Retain this leaf trampoline for process lifetime, including failure paths.
  physics_thunk = storage;
  std::memcpy(call, patched.data(), patched.size());
  const BOOL flushed = FlushInstructionCache(GetCurrentProcess(), call, patched.size());
  DWORD ignored = 0;
  const BOOL protected_again = VirtualProtect(call, patched.size(), old_protection, &ignored);
  if (!flushed || !protected_again) {
    DWORD restore_protection = 0;
    if (VirtualProtect(call, original.size(), PAGE_EXECUTE_READWRITE, &restore_protection)) {
      std::memcpy(call, original.data(), original.size());
      FlushInstructionCache(GetCurrentProcess(), call, original.size());
      VirtualProtect(call, original.size(), old_protection, &ignored);
    }
    return false;
  }
  completionist::AppendBridgeLog(
      "COLLECTIBLE_UI_PHYSICS_CAPACITY_READY world=7 native_slots=500 slots=2048 engine_allocation=true");
  return true;
}

BOOL CALLBACK Initialize(PINIT_ONCE, PVOID, PVOID*) {
  std::wstring system_path;
  if (!completionist::BuildSystemDxgiPath(&system_path, &failure)) return TRUE;
  HMODULE system = LoadLibraryExW(system_path.c_str(), nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (system == nullptr) {
    failure = GetLastError();
    completionist::AppendBridgeLog("COLLECTIBLE_DXGI_REJECTED reason=system_load error=" +
                                  std::to_string(failure));
    return TRUE;
  }
  if (!completionist::ResolveDxgiExportsByName(system, &exports, &failure)) return TRUE;
  // Native checks must not break graphics. Keep System32 fallback ready.
  std::wstring exe, root;
  DWORD error = 0;
  completionist::Sha256 digest{};
  std::string reason;
  if (!completionist::BuildModulePath(&exe, &error) ||
      !completionist::BuildModuleDirectory(&root, &error)) {
    completionist::AppendBridgeLog("COLLECTIBLE_CAPACITY_REJECTED reason=exe_path error=" +
                                  std::to_string(error));
    return TRUE;
  }
  if (!completionist::Sha256File(exe, &digest, &reason)) {
    completionist::AppendBridgeLog("COLLECTIBLE_CAPACITY_REJECTED reason=" + reason);
    return TRUE;
  }
  if (!completionist::IsSupportedExecutableHash(digest)) {
    completionist::AppendBridgeLog("COLLECTIBLE_CAPACITY_REJECTED reason=unsupported_exe sha256=" +
                                  completionist::Sha256Hex(digest) + " native_patches=false graphics_forwarded=true");
    return TRUE;
  }
  const std::wstring upstream = root + L"\\mods\\completionist-map\\native\\collectible-base-dxgi.dll";
  if (!completionist::Sha256File(upstream, &digest, &reason) ||
      completionist::Sha256Hex(digest) != kUpstreamHash) {
    completionist::AppendBridgeLog("COLLECTIBLE_CAPACITY_REJECTED reason=upstream_hash");
    return TRUE;
  }
  HMODULE module = LoadLibraryExW(upstream.c_str(), nullptr,
                                LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (module == nullptr) {
    completionist::AppendBridgeLog("COLLECTIBLE_CAPACITY_REJECTED reason=upstream_load error=" +
                                  std::to_string(GetLastError()));
    return TRUE;
  }
  std::array<FARPROC, completionist::kDxgiExports.size()> resolved{};
  for (std::size_t i=0; i<resolved.size(); ++i) {
    const auto& item = completionist::kDxgiExports[i];
    resolved[i] = GetProcAddress(module, MAKEINTRESOURCEA(item.ordinal));
    if (resolved[i] == nullptr || resolved[i] != GetProcAddress(module, std::string(item.name).c_str())) {
      completionist::AppendBridgeLog("COLLECTIBLE_CAPACITY_REJECTED reason=upstream_exports");
      return TRUE;
    }
  }
  FARPROC snapshot_export = GetProcAddress(module, "CompletionistMapGetRavenSnapshotV1");
  if (snapshot_export == nullptr ||
      !ExpandCapacity(reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr))) ||
      !ExpandEntityArray(reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr))) ||
      !ExpandUiPhysics(reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr)))) {
    completionist::AppendBridgeLog("COLLECTIBLE_CAPACITY_REJECTED reason=native_setup graphics_forwarded=true");
    return TRUE;
  }
  exports = resolved;
  snapshot = snapshot_export;
  failure = ERROR_SUCCESS;
  completionist::AppendBridgeLog("COLLECTIBLE_CAPACITY_FORWARD_READY upstream=original_raven_nornir_bridge exports=20");
  return TRUE;
}

extern "C" HRESULT WINAPI ForwardingFailure() {
  return HRESULT_FROM_WIN32(failure == ERROR_SUCCESS ? ERROR_PROC_NOT_FOUND : failure);
}
}

extern "C" FARPROC CompletionistResolveDxgiExport(unsigned int ordinal) {
  InitOnceExecuteOnce(&once, Initialize, nullptr, nullptr);
  if (failure == ERROR_SUCCESS) {
    for (std::size_t i=0; i<exports.size(); ++i)
      if (completionist::kDxgiExports[i].ordinal == ordinal && exports[i] != nullptr) return exports[i];
  }
  return reinterpret_cast<FARPROC>(&ForwardingFailure);
}

extern "C" BOOL WINAPI CompletionistMapGetRavenSnapshotV1(void* output) {
  InitOnceExecuteOnce(&once, Initialize, nullptr, nullptr);
  if (failure != ERROR_SUCCESS || snapshot == nullptr) return FALSE;
  using ReadSnapshot = BOOL(WINAPI*)(void*);
  return reinterpret_cast<ReadSnapshot>(snapshot)(output);
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
  return TRUE;
}
