cmake_minimum_required(VERSION 3.24)
project(collectible_marker_capacity LANGUAGES CXX ASM_MASM)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
if(NOT WIN32 OR NOT MSVC OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "This shim requires Windows x64 and MSVC")
endif()
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(BRIDGE "${CMAKE_CURRENT_SOURCE_DIR}/../raven-authority-bridge")
set(GENERATED "${CMAKE_CURRENT_BINARY_DIR}/generated")
add_custom_command(
  OUTPUT "${GENERATED}/dxgi.def" "${GENERATED}/dxgi.asm" "${GENERATED}/dxgi_contract.generated.h"
  COMMAND ${Python3_EXECUTABLE} "${BRIDGE}/tools/generate_dxgi_proxy.py"
    --contract "${BRIDGE}/dxgi-export-contract.json"
    --def-output "${GENERATED}/dxgi.def"
    --asm-output "${GENERATED}/dxgi.asm"
    --header-output "${GENERATED}/dxgi_contract.generated.h"
  DEPENDS "${BRIDGE}/tools/generate_dxgi_proxy.py" "${BRIDGE}/dxgi-export-contract.json"
  VERBATIM)
add_library(collectible_capacity SHARED proxy.cpp capacity.cpp
  "${BRIDGE}/src/hash.cpp" "${BRIDGE}/src/platform.cpp"
  "${GENERATED}/dxgi.def" "${GENERATED}/dxgi.asm")
target_compile_features(collectible_capacity PRIVATE cxx_std_20)
target_include_directories(collectible_capacity PRIVATE "${BRIDGE}/src" "${GENERATED}")
target_compile_definitions(collectible_capacity PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX UNICODE _UNICODE)
set(COLLECTIBLE_UPSTREAM_SHA256 "cc91a2ea4475c83085488c33bb0ece223f958054c1a4ac71d26d67a31a84f7b7" CACHE STRING "Exact companion DLL SHA256")
string(LENGTH "${COLLECTIBLE_UPSTREAM_SHA256}" UPSTREAM_HASH_LENGTH)
if(NOT UPSTREAM_HASH_LENGTH EQUAL 64 OR NOT COLLECTIBLE_UPSTREAM_SHA256 MATCHES "^[0-9a-f]+$")
  message(FATAL_ERROR "Invalid companion SHA256")
endif()
target_compile_definitions(collectible_capacity PRIVATE COLLECTIBLE_UPSTREAM_SHA256="${COLLECTIBLE_UPSTREAM_SHA256}")
target_compile_options(collectible_capacity PRIVATE $<$<COMPILE_LANGUAGE:CXX>:/W4 /WX /permissive- /EHsc /guard:cf>)
target_link_options(collectible_capacity PRIVATE /DYNAMICBASE /NXCOMPAT /GUARD:CF)
target_link_libraries(collectible_capacity PRIVATE bcrypt)
set_target_properties(collectible_capacity PROPERTIES OUTPUT_NAME dxgi PREFIX "")
include(CTest)
add_executable(capacity_tests capacity_tests.cpp capacity.cpp physics_test_caller.asm)
target_compile_features(capacity_tests PRIVATE cxx_std_20)
target_compile_definitions(capacity_tests PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
target_compile_options(capacity_tests PRIVATE $<$<COMPILE_LANGUAGE:CXX>:/W4 /WX /permissive- /EHsc>)
add_test(NAME capacity_tests COMMAND capacity_tests)
add_executable(capacity_forwarding_tests "${BRIDGE}/tests/forwarding_tests.cpp")
target_compile_features(capacity_forwarding_tests PRIVATE cxx_std_20)
target_include_directories(capacity_forwarding_tests PRIVATE "${GENERATED}")
target_compile_definitions(capacity_forwarding_tests PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX UNICODE _UNICODE)
target_compile_options(capacity_forwarding_tests PRIVATE /W4 /WX /permissive- /EHsc)
target_link_libraries(capacity_forwarding_tests PRIVATE psapi)
add_dependencies(capacity_forwarding_tests collectible_capacity)
add_test(NAME capacity_forwarding_tests COMMAND capacity_forwarding_tests $<TARGET_FILE:collectible_capacity>)
add_test(NAME capacity_windows10_forwarding_tests
  COMMAND capacity_forwarding_tests $<TARGET_FILE:collectible_capacity> --simulate-windows10)
