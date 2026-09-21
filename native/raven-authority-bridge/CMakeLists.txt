cmake_minimum_required(VERSION 3.24)

project(completionist_raven_authority_bridge LANGUAGES CXX)

set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "Raven authority bridge needs 64-bit Windows")
endif()

add_library(raven_authority_bridge SHARED
  src/dxgi_proxy.cpp
  src/platform.cpp
  src/dxgi_proxy.def
)
target_compile_features(raven_authority_bridge PRIVATE cxx_std_20)
target_include_directories(raven_authority_bridge PRIVATE src)
target_compile_definitions(raven_authority_bridge PRIVATE
  WIN32_LEAN_AND_MEAN
  NOMINMAX
  UNICODE
  _UNICODE
)
if(MSVC)
  target_compile_options(raven_authority_bridge PRIVATE /W4 /WX /permissive- /EHsc /guard:cf)
  target_link_options(raven_authority_bridge PRIVATE /DYNAMICBASE /NXCOMPAT /GUARD:CF)
endif()
set_target_properties(raven_authority_bridge PROPERTIES
  OUTPUT_NAME dxgi
  PREFIX ""
)

include(CTest)
if(BUILD_TESTING)
  add_executable(raven_bridge_platform_tests
    tests/platform_tests.cpp
    src/platform.cpp
  )
  target_compile_features(raven_bridge_platform_tests PRIVATE cxx_std_20)
  target_include_directories(raven_bridge_platform_tests PRIVATE src)
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
endif()
