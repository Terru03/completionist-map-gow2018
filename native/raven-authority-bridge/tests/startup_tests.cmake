# Exercise the same proxy code with a loader callback before static CRT startup.
function(add_dxgi_startup_tests proxy forwarding)
  get_target_property(proxy_sources ${proxy} SOURCES)
  add_library(${proxy}_early_fixture SHARED ${proxy_sources}
    "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/early_appcompat_callback.cpp")
  foreach(property INCLUDE_DIRECTORIES COMPILE_DEFINITIONS COMPILE_OPTIONS LINK_OPTIONS LINK_LIBRARIES)
    set_property(TARGET ${proxy}_early_fixture PROPERTY ${property}
      "$<TARGET_PROPERTY:${proxy},${property}>")
  endforeach()
  target_compile_features(${proxy}_early_fixture PRIVATE cxx_std_20)
  add_dependencies(${proxy}_early_fixture ${proxy})
  set_target_properties(${proxy}_early_fixture PROPERTIES OUTPUT_NAME early_dxgi PREFIX "")
  add_test(NAME ${proxy}_early_appcompat
    COMMAND ${forwarding} $<TARGET_FILE:${proxy}_early_fixture>)
  add_test(NAME ${proxy}_appcompat_replay
    COMMAND ${forwarding} $<TARGET_FILE:${proxy}> --appcompat-replay)
  set_tests_properties(${proxy}_early_appcompat ${proxy}_appcompat_replay PROPERTIES TIMEOUT 30)

endfunction()
