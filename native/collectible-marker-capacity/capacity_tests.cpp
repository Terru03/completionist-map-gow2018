#include "capacity.h"
#include <algorithm>
#include <array>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <windows.h>

extern "C" std::uint64_t InvokePhysicsThunk(void* parameters, std::uint32_t world, void* thunk);

std::uint64_t MeasurePhysicsParameters(const std::uint8_t* parameters) {
  std::uint32_t bodies, shapes;
  std::memcpy(&bodies, parameters+0x14, 4);
  std::memcpy(&shapes, parameters+0x1c, 4);
  return static_cast<std::uint64_t>(bodies)*160 + static_cast<std::uint64_t>(shapes)*80;
}

void Check(bool ok) { if (!ok) throw std::runtime_error("capacity regression"); }
bool Insert(std::vector<collectible::Slot>& slots, std::uint64_t id) {
  const auto start = id % slots.size();
  auto i = start;
  do {
    if (slots[i].id == id) return true;
    if (!slots[i].id) { slots[i] = {id, 123}; return true; }
    i = (i+1)%slots.size();
  } while (i != start);
  return false;
}
int main() {
  collectible::Code code{}, patched{};
  const std::array<std::uint8_t,18> prefix{0x48,0x8d,0x0d,0xa9,0x3f,0x5e,0x02,
    0x48,0xc7,0x05,0x7e,0x3f,0x5e,0x02,0xdb,0x02,0x00,0x00};
  std::copy(prefix.begin(),prefix.end(),code.begin());
  const std::array<std::uint8_t,5> clear{0xb8,0xdc,0x02,0x00,0x00};
  std::copy(clear.begin(),clear.end(),code.begin()+0x5b);
  constexpr std::uintptr_t location=0x1406c2298, storage=0x148000000;
  Check(collectible::MakeConstructorPatch(code,location,storage,&patched));
  std::int32_t delta; std::uint32_t maximum,count;
  std::memcpy(&delta,patched.data()+3,4); std::memcpy(&maximum,patched.data()+14,4);
  std::memcpy(&count,patched.data()+0x5c,4);
  Check(location+7+delta==storage && maximum+1==count && count==2048);
  for (std::size_t i=0;i<code.size();++i)
    if (!((i>=3&&i<7)||(i>=14&&i<18)||(i>=0x5c&&i<0x60))) Check(code[i]==patched[i]);
  auto invalid=code; invalid[7]^=1; auto unchanged=patched;
  Check(!collectible::MakeConstructorPatch(invalid,location,storage,&patched) && patched==unchanged);
  Check(!collectible::MakeConstructorPatch(code,location,0x700000000000,&patched));
  collectible::Registry registry{};
  Check(collectible::IsEmptyNativeRegistry(registry,location));
  registry.slots=reinterpret_cast<collectible::Slot*>(location+40); registry.last_slot=731;
  Check(collectible::IsEmptyNativeRegistry(registry,location));
  registry.count=1; Check(!collectible::IsEmptyNativeRegistry(registry,location));
  registry.count=0;registry.slots=nullptr;Check(!collectible::IsEmptyNativeRegistry(registry,location));
  std::vector<collectible::Slot> native(732), grown(count);
  for (std::uint64_t id=1;id<=922;++id) {
    // Deliberate collisions exercise wraparound under the native probe rule.
    const auto key=id*2048+2047;
    Check(Insert(native,key)==(id<=732)); Check(Insert(grown,key)); Check(Insert(grown,key));
  }
  Check(std::count_if(grown.begin(),grown.end(),[](auto row){return row.id!=0;})==922);
  // Captured instructions from the supported executable, including all
  // readers and the sole array insertion site (0x61bd26).
  constexpr std::array<collectible::Reference, 7> references{{
    {0x48,0x8d,0x05,0xfb,0xa5,0xca,0x01}, {0x48,0x8d,0x05,0xb4,0x9c,0xca,0x01},
    {0x4c,0x8d,0x35,0x17,0x93,0xca,0x01}, {0x4c,0x8d,0x35,0x0c,0x8c,0xca,0x01},
    {0x48,0x8d,0x0d,0x86,0x89,0xca,0x01}, {0x4c,0x8d,0x35,0xd3,0x7f,0xca,0x01},
    {0x48,0x8d,0x35,0x99,0x77,0xca,0x01}}};
  constexpr std::uintptr_t base = 0x140000000;
  for (std::size_t i=0; i<references.size(); ++i) {
    collectible::Reference result{};
    Check(collectible::MakeEntityReferencePatch(references[i],i,base,storage,&result));
    Check(std::equal(result.begin(),result.begin()+3,references[i].begin()));
    std::memcpy(&delta,result.data()+3,4);
    Check(base+collectible::kEntityReferences[i]+7+delta==storage);
    auto bad=references[i]; bad[3]^=1;
    const auto expected=result;
    Check(!collectible::MakeEntityReferencePatch(bad,i,base,storage,&result) && result==expected);
    Check(!collectible::MakeEntityReferencePatch(references[i],i,base,0x700000000000,&result));
  }
  static_assert(collectible::kEntitySlots >= 512+410);
  // Execute the generated leaf thunk, with a stand-in for the native sizing
  // function. Only UI world 7 may change; the whole parameter block and the
  // sizing function's return value are checked for every world.
  constexpr collectible::PhysicsCall physics_call{0xe8,0xfd,0x73,0x0a,0x00};
  collectible::PhysicsCall new_call{};
  collectible::PhysicsThunk thunk{};
  Check(collectible::MakeUiPhysicsPatch(physics_call,base,storage,&new_call,&thunk));
  std::memcpy(&delta,new_call.data()+1,4);
  Check(base+collectible::kPhysicsSizeCallRva+5+delta==storage);
  std::uintptr_t native_target=0;
  std::memcpy(&native_target,thunk.data()+25,8);
  Check(native_target==base+collectible::kPhysicsSizeRva);
  const auto expected_call=new_call;
  const auto expected_thunk=thunk;
  auto bad_call=physics_call; bad_call[1]^=1;
  Check(!collectible::MakeUiPhysicsPatch(bad_call,base,storage,&new_call,&thunk));
  Check(new_call==expected_call && thunk==expected_thunk);
  Check(!collectible::MakeUiPhysicsPatch(physics_call,base,0x700000000000,&new_call,&thunk));
  Check(new_call==expected_call && thunk==expected_thunk);
  const auto measure=reinterpret_cast<std::uintptr_t>(&MeasurePhysicsParameters);
  std::memcpy(thunk.data()+25,&measure,8);
  void* executable=VirtualAlloc(nullptr,thunk.size(),MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
  Check(executable!=nullptr);
  std::memcpy(executable,thunk.data(),thunk.size());
  DWORD protection=0;
  Check(VirtualProtect(executable,thunk.size(),PAGE_EXECUTE_READ,&protection)!=FALSE);
  Check(FlushInstructionCache(GetCurrentProcess(),executable,thunk.size())!=FALSE);
  for (std::uint32_t world=0;world<9;++world) {
    std::array<std::uint8_t,0xa0> parameters{};
    parameters.fill(0xa5);
    const std::uint32_t original_bodies=500,original_shapes=500;
    std::memcpy(parameters.data()+0x14,&original_bodies,4);
    std::memcpy(parameters.data()+0x1c,&original_shapes,4);
    auto expected_parameters=parameters;
    if (world==7) {
      std::memcpy(expected_parameters.data()+0x14,&collectible::kUiPhysicsSlots,4);
      std::memcpy(expected_parameters.data()+0x1c,&collectible::kUiPhysicsSlots,4);
    }
    const auto bytes=InvokePhysicsThunk(parameters.data(),world,executable);
    Check(parameters==expected_parameters);
    Check(bytes==MeasurePhysicsParameters(expected_parameters.data()));
  }
  Check(VirtualFree(executable,0,MEM_RELEASE)!=FALSE);
  std::cout<<"CAPACITY_TESTS_OK marker_slots=2048 markers=922 entity_slots=4096 references=7 ui_physics_slots=2048\n";
}
