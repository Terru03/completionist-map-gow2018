cmake_minimum_required(VERSION 3.24)

project(completionist_raven_authority_bridge LANGUAGES CXX ASM_MASM)

set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8 OR NOT MSVC)
  message(FATAL_ERROR "Raven authority bridge needs 64-bit Windows and MSVC")
endif()

include(FetchContent)
set(ZLIB_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SKIP_INSTALL_ALL ON CACHE BOOL "" FORCE)
FetchContent_Declare(zlib
  GIT_REPOSITORY https://github.com/madler/zlib.git
  GIT_TAG 925af44f3cde53c6b076611c297850091b5dc7bb
  GIT_SHALLOW TRUE
)
FetchContent_MakeAvailable(zlib)

find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../..")
set(CAPTURE_ROOT "${REPO_ROOT}/archive/field-logs/runtime-captures/staged-wad-bitstream-raven-20260921-060345-c2c9bcc1")
set(GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(GENERATED_CATALOGUE "${GENERATED_DIR}/raven_catalogue.generated.h")
set(GENERATED_FIXTURE "${GENERATED_DIR}/raven_fixture.generated.h")
set(XINPUT_CONTRACT "${CMAKE_CURRENT_SOURCE_DIR}/xinput1_4-export-contract.json")
set(GENERATED_XINPUT_DEF "${GENERATED_DIR}/xinput_proxy.def")
set(GENERATED_XINPUT_ASM "${GENERATED_DIR}/xinput_thunks.asm")
set(GENERATED_XINPUT_HEADER "${GENERATED_DIR}/xinput_contract.generated.h")
add_custom_command(
  OUTPUT "${GENERATED_CATALOGUE}" "${GENERATED_FIXTURE}"
  COMMAND ${CMAKE_COMMAND} -E make_directory "${GENERATED_DIR}"
  COMMAND ${Python3_EXECUTABLE}
          "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_bridge_data.py"
          --catalogue "${REPO_ROOT}/catalogue/odins-ravens-gameobject-identities.json"
          --replay "${CAPTURE_ROOT}/replay-report.json"
          --catalogue-output "${GENERATED_CATALOGUE}"
          --fixture-output "${GENERATED_FIXTURE}"
  DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_bridge_data.py"
    "${REPO_ROOT}/catalogue/odins-ravens-gameobject-identities.json"
    "${CAPTURE_ROOT}/replay-report.json"
  VERBATIM
)
add_custom_target(raven_bridge_generated_data
  DEPENDS "${GENERATED_CATALOGUE}" "${GENERATED_FIXTURE}"
)
add_custom_command(
  OUTPUT "${GENERATED_XINPUT_DEF}" "${GENERATED_XINPUT_ASM}" "${GENERATED_XINPUT_HEADER}"
  COMMAND ${Python3_EXECUTABLE}
          "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_xinput_proxy.py"
          --contract "${XINPUT_CONTRACT}"
          --def-output "${GENERATED_XINPUT_DEF}"
          --asm-output "${GENERATED_XINPUT_ASM}"
          --header-output "${GENERATED_XINPUT_HEADER}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_xinput_proxy.py" "${XINPUT_CONTRACT}"
  VERBATIM
)
add_custom_target(raven_bridge_generated_proxy
  DEPENDS "${GENERATED_XINPUT_DEF}" "${GENERATED_XINPUT_ASM}" "${GENERATED_XINPUT_HEADER}"
)

add_library(raven_authority_bridge SHARED
  src/authority_decoder.cpp
  src/authority_runtime.cpp
  src/hash.cpp
  src/snapshot_store.cpp
  src/xinput_proxy.cpp
  src/platform.cpp
  "${GENERATED_XINPUT_DEF}"
  "${GENERATED_XINPUT_ASM}"
)
add_dependencies(raven_authority_bridge raven_bridge_generated_data raven_bridge_generated_proxy)
target_compile_features(raven_authority_bridge PRIVATE cxx_std_20)
target_include_directories(raven_authority_bridge PRIVATE
  src
  "${GENERATED_DIR}"
  "${zlib_SOURCE_DIR}"
  "${zlib_BINARY_DIR}"
)
target_link_libraries(raven_authority_bridge PRIVATE zlibstatic bcrypt)
target_compile_definitions(raven_authority_bridge PRIVATE
  WIN32_LEAN_AND_MEAN
  NOMINMAX
  UNICODE
  _UNICODE
)
if(MSVC)
  target_compile_options(raven_authority_bridge PRIVATE
    $<$<COMPILE_LANGUAGE:CXX>:/W4 /WX /permissive- /EHsc /guard:cf>
  )
  target_link_options(raven_authority_bridge PRIVATE /DYNAMICBASE /NXCOMPAT /GUARD:CF)
endif()
set_target_properties(raven_authority_bridge PROPERTIES
  OUTPUT_NAME XINPUT1_4
  PREFIX ""
)

include(CTest)
if(BUILD_TESTING)
  add_executable(raven_bridge_platform_tests
    tests/platform_tests.cpp
    src/hash.cpp
    src/platform.cpp
  )
  add_dependencies(raven_bridge_platform_tests raven_bridge_generated_data)
  target_compile_features(raven_bridge_platform_tests PRIVATE cxx_std_20)
  target_include_directories(raven_bridge_platform_tests PRIVATE src "${GENERATED_DIR}")
  target_link_libraries(raven_bridge_platform_tests PRIVATE bcrypt)
  target_compile_definitions(raven_bridge_platform_tests PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    UNICODE
    _UNICODE
  )
  if(MSVC)
    target_compile_options(raven_bridge_platform_tests PRIVATE /W4 /WX /permissive- /EHsc)
  endif()
  add_test(NAME raven_bridge_platform_tests COMMAND raven_bridge_platform_tests)

  add_executable(raven_bridge_forwarding_tests
    tests/forwarding_tests.cpp
  )
  target_compile_features(raven_bridge_forwarding_tests PRIVATE cxx_std_20)
  target_compile_definitions(raven_bridge_forwarding_tests PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    UNICODE
    _UNICODE
  )
  if(MSVC)
    target_compile_options(raven_bridge_forwarding_tests PRIVATE /W4 /WX /permissive- /EHsc)
  endif()
  add_dependencies(raven_bridge_forwarding_tests raven_authority_bridge)
  add_test(NAME raven_bridge_forwarding_tests
    COMMAND raven_bridge_forwarding_tests $<TARGET_FILE:raven_authority_bridge>
  )

  add_executable(raven_bridge_export_contract_tests
    tests/export_contract_tests.cpp
    src/platform.cpp
  )
  add_dependencies(raven_bridge_export_contract_tests raven_authority_bridge raven_bridge_generated_proxy)
  target_compile_features(raven_bridge_export_contract_tests PRIVATE cxx_std_20)
  target_include_directories(raven_bridge_export_contract_tests PRIVATE src "${GENERATED_DIR}")
  target_link_libraries(raven_bridge_export_contract_tests PRIVATE dbghelp)
  target_compile_definitions(raven_bridge_export_contract_tests PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    UNICODE
    _UNICODE
  )
  if(MSVC)
    target_compile_options(raven_bridge_export_contract_tests PRIVATE /W4 /WX /permissive- /EHsc)
  endif()
  add_test(NAME raven_bridge_export_contract_tests
    COMMAND raven_bridge_export_contract_tests $<TARGET_FILE:raven_authority_bridge>
  )

  add_executable(raven_bridge_import_probe
    tools/live_import_probe.cpp
  )
  target_compile_features(raven_bridge_import_probe PRIVATE cxx_std_20)
  target_link_libraries(raven_bridge_import_probe PRIVATE psapi)
  target_compile_definitions(raven_bridge_import_probe PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    UNICODE
    _UNICODE
  )
  if(MSVC)
    target_compile_options(raven_bridge_import_probe PRIVATE /W4 /WX /permissive- /EHsc)
  endif()

  add_executable(raven_bridge_authority_tests
    tests/authority_tests.cpp
    src/authority_decoder.cpp
    src/snapshot_store.cpp
  )
  add_dependencies(raven_bridge_authority_tests raven_bridge_generated_data)
  target_compile_features(raven_bridge_authority_tests PRIVATE cxx_std_20)
  target_include_directories(raven_bridge_authority_tests PRIVATE
    src
    "${GENERATED_DIR}"
    "${zlib_SOURCE_DIR}"
    "${zlib_BINARY_DIR}"
  )
  target_link_libraries(raven_bridge_authority_tests PRIVATE zlibstatic)
  target_compile_definitions(raven_bridge_authority_tests PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    UNICODE
    _UNICODE
    COMPLETIONIST_FIXTURE_ROOT=L"${CAPTURE_ROOT}"
  )
  if(MSVC)
    target_compile_options(raven_bridge_authority_tests PRIVATE /W4 /WX /permissive- /EHsc)
  endif()
  add_test(NAME raven_bridge_authority_tests COMMAND raven_bridge_authority_tests)
endif()
