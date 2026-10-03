# Startup Crash Fix Plan

> For agentic workers: Use Superpowers executing-plans. Run each test before fix, then after fix. Use requesting-code-review before final checks.

**Goal:** Fix launch failure in Completionist Map v1.0.0. Keep map, compass, and collected state working.

**Architecture:** Both DXGI layers must resolve system functions by name. Missing optional functions must not block graphics. Keep exact game hash and companion hash checks for native patches; log any rejected setup. Installer must check game hash before it writes mod files.

**Tech Stack:** C++20, MSVC, MASM, CMake/CTest, Python, Windows PowerShell 5.1.

**Spec:** User request and Nexus issue 1143859. Fault at GoW.exe+0x999ED4 dereferences graphics object. Failed DXGI factory fits this fault; reporter OS and memory dump not supplied. Removing proxy exposes separate engine marker dictionary limit.

## Constraints

- Keep user changes in CHANGELOG.md.
- Do not change saves or grant progress.
- Do not weaken native patch hash checks.
- Keep System32 DLL load path fixed.
- Do not post replies or upload release without user request.
- Test on this PC first. Flag laptop need if real OS or game build remains untested.

## Task 1: Reproduce DXGI Failures

Files: native/raven-authority-bridge/tests/forwarding_tests.cpp and both native CMakeLists.txt files.

- [x] Add --simulate-windows10 to forwarding test. In test only, replace proxy GetProcAddress import with a Windows 10-shaped lookup: omit DXGIDisableVBlankVirtualization and shift later system ordinals.
- [x] Call all three real graphics factories through shipped companion. Expect non-null COM objects. Run against old code; expect safe factory forwarding failure.
- [x] Run same factory test against shipped capacity proxy from an unsupported host. Old code already fails this check.

## Task 2: Fix Both DXGI Layers

Files: native/raven-authority-bridge/src/dxgi_proxy.cpp, shared dxgi_forwarding.h, native/collectible-marker-capacity/proxy.cpp.

- [x] Resolve each system export by name. Require CreateDXGIFactory, CreateDXGIFactory1, and CreateDXGIFactory2 only.
- [x] Give missing optional exports ERROR_PROC_NOT_FOUND without changing working factory state.
- [x] Resolve System32 forwarding before native patch checks. Reject unknown EXE or bad companion with clear log; keep graphics forwarding intact and snapshot unavailable.
- [x] Build both DLLs in fresh build directories. Bind capacity proxy to new companion SHA256.
- [x] Run normal and Windows 10-shaped factory tests for both DLLs, plus native capacity and authority tests.

## Task 3: Build and Test Release

Files: tools/build-nexus-package.py, tools/test_nexus_package.py, docs/builds/startup-compatibility.md.

- [x] Add preflight for exact EXE hash before installer backup/copy. Test unsupported EXE leaves target untouched.
- [x] Build v1.0.1 from original published resources and newly built native DLLs. Keep v1.0.0 ZIP intact.
- [x] Verify all ZIP payload hashes and DLL companion pin. Inspect boot artwork setup for manual and Vortex paths.
- [ ] Back up current native DLLs. Install exact candidate reversibly. Launch real game, load save, open map, track marker, reopen map, and quit.
- [x] Get independent code review. Fix issues; run fresh relevant checks. Report evidence and any platform gap.

Review done. Builder input/output overlap fix verified. Local game launch and save load done twice. Fresh 22 checks passed after full quit. Map/compass UI check remains pending: tool key input not reaching game. User asked for one local map open; no laptop download needed for regression tests.
