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
set(CAPTURE_ROOT "${REPO_ROOT}/archive/field-logs/runtime-captures/staged-wad-bitstream-raven-20260921-060345-c2c9bcc1"
    CACHE PATH "Staged checkpoint fixture root for native tests")
set(GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(GENERATED_CATALOGUE "${GENERATED_DIR}/raven_catalogue.generated.h")
set(GENERATED_FIXTURE "${GENERATED_DIR}/raven_fixture.generated.h")
set(DXGI_CONTRACT "${CMAKE_CURRENT_SOURCE_DIR}/dxgi-export-contract.json")
set(GENERATED_DXGI_DEF "${GENERATED_DIR}/dxgi_proxy.def")
set(GENERATED_DXGI_ASM "${GENERATED_DIR}/dxgi_thunks.asm")
set(GENERATED_DXGI_HEADER "${GENERATED_DIR}/dxgi_contract.generated.h")
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
  OUTPUT "${GENERATED_DXGI_DEF}" "${GENERATED_DXGI_ASM}" "${GENERATED_DXGI_HEADER}"
  COMMAND ${Python3_EXECUTABLE}
          "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_dxgi_proxy.py"
          --contract "${DXGI_CONTRACT}"
          --def-output "${GENERATED_DXGI_DEF}"
          --asm-output "${GENERATED_DXGI_ASM}"
          --header-output "${GENERATED_DXGI_HEADER}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_dxgi_proxy.py" "${DXGI_CONTRACT}"
  VERBATIM
)
add_custom_target(raven_bridge_generated_proxy
  DEPENDS "${GENERATED_DXGI_DEF}" "${GENERATED_DXGI_ASM}" "${GENERATED_DXGI_HEADER}"
)

set(GENERATED_NORNIR "${GENERATED_DIR}/nornir_catalogue.generated.h")
add_custom_command(
  OUTPUT "${GENERATED_NORNIR}"
  COMMAND ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_nornir_data.py"
          --output "${GENERATED_NORNIR}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_nornir_data.py"
          "${REPO_ROOT}/tools/v0.10.5/nornir_saved_state.py"
          "${REPO_ROOT}/tools/v0.10.5/nornir_catalogue.py"
          "${REPO_ROOT}/config/collectibles/v0.10.5/all-collectibles.json"
  VERBATIM)

set(GENERATED_COLLECTIBLES "${GENERATED_DIR}/collectible_catalogue.generated.h")
add_custom_command(
  OUTPUT "${GENERATED_COLLECTIBLES}"
  COMMAND ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_collectible_data.py"
          --bindings "${REPO_ROOT}/config/collectibles/v0.10.5/completion-bindings.json"
          --output "${GENERATED_COLLECTIBLES}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_collectible_data.py"
          "${REPO_ROOT}/config/collectibles/v0.10.5/completion-bindings.json"
  VERBATIM)

add_library(raven_authority_bridge SHARED
  src/collectible_authority.cpp "${GENERATED_COLLECTIBLES}"
  src/nornir_authority.cpp "${GENERATED_NORNIR}"
  src/authority_decoder.cpp
  src/chest_authority.cpp
  src/authority_runtime.cpp
  src/hash.cpp
  src/snapshot_store.cpp
  src/snapshot_delivery.cpp
  src/dxgi_proxy.cpp
  src/platform.cpp
  "${GENERATED_DXGI_DEF}"
  "${GENERATED_DXGI_ASM}"
)
add_dependencies(raven_authority_bridge raven_bridge_generated_data raven_bridge_generated_proxy)
target_compile_features(raven_authority_bridge PRIVATE cxx_std_20)
target_include_directories(raven_authority_bridge PRIVATE
  src
  "${GENERATED_DIR}"
  "${zlib_SOURCE_DIR}"
  "${zlib_BINARY_DIR}"
)
target_link_libraries(raven_authority_bridge PRIVATE zlibstatic bcrypt ws2_32)
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
  OUTPUT_NAME dxgi
  PREFIX ""
)

include(CTest)
if(BUILD_TESTING)
  add_executable(collectible_authority_tests tests/collectible_authority_tests.cpp
    src/collectible_authority.cpp src/authority_decoder.cpp "${GENERATED_COLLECTIBLES}")
  add_dependencies(collectible_authority_tests raven_bridge_generated_data)
  target_compile_features(collectible_authority_tests PRIVATE cxx_std_20)
  target_include_directories(collectible_authority_tests PRIVATE src "${GENERATED_DIR}"
    "${zlib_SOURCE_DIR}" "${zlib_BINARY_DIR}")
  target_link_libraries(collectible_authority_tests PRIVATE zlibstatic)
  target_compile_definitions(collectible_authority_tests PRIVATE COMPLETIONIST_FIXTURE_ROOT=L"${CAPTURE_ROOT}")
  target_compile_options(collectible_authority_tests PRIVATE /W4 /WX /permissive- /EHsc)
  add_test(NAME collectible_authority_tests COMMAND collectible_authority_tests)
  add_executable(nornir_delivery_tests tests/nornir_delivery_tests.cpp
    src/snapshot_delivery.cpp src/platform.cpp)
  add_dependencies(nornir_delivery_tests raven_bridge_generated_data)
  target_compile_features(nornir_delivery_tests PRIVATE cxx_std_20)
  target_include_directories(nornir_delivery_tests PRIVATE src "${GENERATED_DIR}")
  target_compile_definitions(nornir_delivery_tests PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX UNICODE _UNICODE)
  target_link_libraries(nornir_delivery_tests PRIVATE ws2_32)
  target_compile_options(nornir_delivery_tests PRIVATE /W4 /WX /permissive- /EHsc)
  add_test(NAME nornir_delivery_tests COMMAND nornir_delivery_tests)
  add_executable(nornir_authority_tests tests/nornir_authority_tests.cpp
    src/nornir_authority.cpp src/authority_decoder.cpp "${GENERATED_NORNIR}")
  add_dependencies(nornir_authority_tests raven_bridge_generated_data)
  target_compile_features(nornir_authority_tests PRIVATE cxx_std_20)
  target_include_directories(nornir_authority_tests PRIVATE src "${GENERATED_DIR}"
    "${zlib_SOURCE_DIR}" "${zlib_BINARY_DIR}")
  target_link_libraries(nornir_authority_tests PRIVATE zlibstatic)
  target_compile_definitions(nornir_authority_tests PRIVATE COMPLETIONIST_FIXTURE_ROOT=L"${CAPTURE_ROOT}")
  target_compile_options(nornir_authority_tests PRIVATE /W4 /WX /permissive- /EHsc)
  add_test(NAME nornir_authority_tests COMMAND nornir_authority_tests)
  set(GENERATED_CHESTS "${GENERATED_DIR}/legendary_catalogue.generated.h")
  add_custom_command(
    OUTPUT "${GENERATED_CHESTS}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${GENERATED_DIR}"
    COMMAND ${Python3_EXECUTABLE}
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_chest_data.py"
            --catalogue "${REPO_ROOT}/catalogue/legendary-chest-authority.json"
            --output "${GENERATED_CHESTS}"
    DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_chest_data.py"
            "${REPO_ROOT}/catalogue/legendary-chest-authority.json"
    VERBATIM
  )
  add_executable(legendary_authority_tests
    tests/chest_authority_tests.cpp src/chest_authority.cpp
    src/authority_decoder.cpp "${GENERATED_CHESTS}")
  add_dependencies(legendary_authority_tests raven_bridge_generated_data)
  target_compile_features(legendary_authority_tests PRIVATE cxx_std_20)
  target_include_directories(legendary_authority_tests PRIVATE src
    "${GENERATED_DIR}" "${zlib_SOURCE_DIR}" "${zlib_BINARY_DIR}")
  target_link_libraries(legendary_authority_tests PRIVATE zlibstatic)
  target_compile_definitions(legendary_authority_tests PRIVATE
    COMPLETIONIST_FIXTURE_ROOT=L"${CAPTURE_ROOT}")
  if(MSVC)
    target_compile_options(legendary_authority_tests PRIVATE /W4 /WX /permissive- /EHsc)
  endif()
  add_test(NAME legendary_authority_tests COMMAND legendary_authority_tests)
  add_test(NAME legendary_python_replay
    COMMAND ${Python3_EXECUTABLE}
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_legendary_replay.py")

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
  target_include_directories(raven_bridge_forwarding_tests PRIVATE "${GENERATED_DIR}")
  target_link_libraries(raven_bridge_forwarding_tests PRIVATE psapi)
  target_compile_definitions(raven_bridge_forwarding_tests PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    UNICODE
    _UNICODE
  )
  if(MSVC)
    target_compile_options(raven_bridge_forwarding_tests PRIVATE /W4 /WX /permissive- /EHsc)
  endif()
  add_dependencies(raven_bridge_forwarding_tests raven_authority_bridge raven_bridge_generated_proxy)
  add_test(NAME raven_bridge_forwarding_tests
    COMMAND raven_bridge_forwarding_tests $<TARGET_FILE:raven_authority_bridge>
  )
  add_test(NAME raven_bridge_windows10_forwarding_tests
    COMMAND raven_bridge_forwarding_tests $<TARGET_FILE:raven_authority_bridge> --simulate-windows10
  )
  include(tests/startup_tests.cmake)
  add_dxgi_startup_tests(raven_authority_bridge raven_bridge_forwarding_tests)

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

  add_library(raven_bridge_incomplete_dxgi_fixture SHARED
    tests/incomplete_dxgi_proxy.cpp
    tests/incomplete_dxgi_proxy.def
  )
  target_compile_features(raven_bridge_incomplete_dxgi_fixture PRIVATE cxx_std_20)
  if(MSVC)
    target_compile_options(raven_bridge_incomplete_dxgi_fixture PRIVATE /W4 /WX /permissive- /EHsc)
  endif()
  set_target_properties(raven_bridge_incomplete_dxgi_fixture PROPERTIES
    OUTPUT_NAME incomplete_dxgi
    PREFIX ""
  )
  add_test(NAME raven_bridge_incomplete_dxgi_rejected
    COMMAND raven_bridge_export_contract_tests
            $<TARGET_FILE:raven_bridge_incomplete_dxgi_fixture>
            --expect-rejected
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
    src/platform.cpp
    src/snapshot_store.cpp
    src/snapshot_delivery.cpp
  )
  add_dependencies(raven_bridge_authority_tests raven_bridge_generated_data)
  target_compile_features(raven_bridge_authority_tests PRIVATE cxx_std_20)
  target_include_directories(raven_bridge_authority_tests PRIVATE
    src
    "${GENERATED_DIR}"
    "${zlib_SOURCE_DIR}"
    "${zlib_BINARY_DIR}"
  )
  target_link_libraries(raven_bridge_authority_tests PRIVATE zlibstatic ws2_32)
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
