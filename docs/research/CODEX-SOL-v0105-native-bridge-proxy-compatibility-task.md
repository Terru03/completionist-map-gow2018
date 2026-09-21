# Codex Sol task: harden native bridge proxy compatibility after DXGI startup failure

## Branch

Work only on:

`codex/all-ravens-release-candidate`

Do not merge to `main`.
Do not switch branches.
Commit and push every meaningful stage.

## Read first

Mandatory:

- `archive/field-logs/local-handoffs/raven-authority-handoff-20260920.md`
- `archive/field-logs/runtime-captures/raven-native-bridge-load-proof-20260921-102726/`
- `native/raven-authority-bridge/src/dxgi_proxy.cpp`
- `native/raven-authority-bridge/src/dxgi_proxy.def`
- `tools/v0.10.5/run-raven-authority-bridge-load-proof-and-push.ps1`
- `tools/v0.10.5/install-raven-authority-bridge.ps1`
- `tools/v0.10.5/rollback-raven-authority-bridge.ps1`
- `tools/v0.10.5/recover-raven-authority-bridge-startup.ps1`
- current native authority decoder/runtime sources and tests

Treat the handoff as the source of truth.

## Product state already solved

Do not redo:

- 53-Raven catalogue identity work;
- save/GameObject codec;
- staged authority semantics;
- absent-WAD false semantics;
- native 53-state decoder;
- atomic snapshot store;
- VFS/package.loadlib/GetRef/LoadCheck research;
- Script Loader plugin/API research.

The native authority decoder is already accepted offline:

```text
states=53
explicit=42
absentWadFalse=11
killed=27
alive=26
Veithurgard=false,true,true
```

The current blocker is **proxy compatibility and runtime loading only**.

## Exact runtime failure

The first real load proof failed at Windows loader resolution with:

```text
GoW.exe - Entry Point Not Found

The procedure entry point CreateDXGIFactory2 could not be located
in the dynamic link library C:\WINDOWS\SYSTEM32\d3d11.dll.
```

Failing bridge SHA-256:

```text
2e93c9c711a5c0f622a4b977b4c8f3e4bc81f0e5b1a8640eb2946830d3d2bd2a
```

Failing proxy exported only:

```text
CreateDXGIFactory1
CompletionistMapGetRavenSnapshotV1
```

The recovery tool removed the bridge and normal GoW startup was confirmed afterward.

Therefore:

**the single-export DXGI proxy design is closed. Do not reinstall or revive it.**

## Second bug discovered

The live proof runner also threw:

```text
The property 'Count' cannot be found on this object.
```

under strict mode after the failed launch sequence.

Fix this independently. Audit every place where a PowerShell pipeline may collapse to a scalar/string and then be accessed via `.Count`. Wrap pipeline results with `@(...)` or use robust collection handling.

Add regression tests for zero, one, and multiple log/process matches.

## Mission

Use one long Sol implementation pass to produce a proxy architecture that is safe enough for a second live test.

The agent must:

1. determine the complete compatibility contract for candidate proxy DLLs;
2. compare:
   - compatibility-complete `dxgi.dll`
   - compatibility-complete `XINPUT1_4.dll`
3. choose the lower-risk architecture based on actual export/import requirements;
4. implement the chosen proxy completely enough that Windows/system modules/overlays cannot fail simply because required public exports are missing;
5. preserve the existing Raven authority reader unchanged except for load integration;
6. fix the runtime proof runner's `.Count` bug;
7. add offline tests that would have rejected the previous minimal proxy before live installation;
8. push a second reversible runtime proof only when offline compatibility gates pass.

## Architecture comparison requirements

### DXGI candidate

Do not judge DXGI compatibility solely from `GoW.exe`'s direct import table.

A local `dxgi.dll` is process-global and can satisfy imports/resolutions from:

- `d3d11.dll`;
- graphics runtime modules;
- overlays;
- ReShade-like tools;
- capture software;
- other injected modules.

If keeping DXGI:

- inspect the real System32 DXGI export surface on the user's Windows version or use the Windows SDK import library/export contract;
- forward all public exports required for transparent proxy compatibility, not just GoW's direct import;
- at minimum prove `CreateDXGIFactory`, `CreateDXGIFactory1`, `CreateDXGIFactory2`, and any other standard exported functions needed by common consumers;
- prefer linker forwarding/thunks or generated forwarding over handwritten ABI wrappers where possible;
- intercept only one safe initialization point;
- do not alter factory semantics.

### XINPUT1_4 candidate

Static GoW import evidence shows:

```text
XINPUT1_4.dll
  normal import
  ordinals 2 and 3
```

Do not assume that two ordinals are the whole proxy contract.

If choosing XInput:

- determine the complete `XINPUT1_4.dll` export surface for the target Windows SDK/system DLL;
- forward all normal named/ordinal exports transparently;
- verify ordinal preservation exactly;
- avoid breaking controllers, overlays, Steam Input, or system consumers;
- initialize Completionist Map separately from the forwarded XInput calls if needed.

## Decision rule

Prefer the candidate with:

1. smaller complete public export surface;
2. lower process-wide dependency risk;
3. simpler ABI-transparent forwarding;
4. fewer conflicts with common mod/overlay tooling;
5. simpler reversible install ownership.

Document the comparison and chosen result in:

`docs/research/v0105-raven-native-bridge.md`

Do not choose based only on what is easiest to code.

## Offline compatibility gate — mandatory before live install

Add a test/tool that validates the produced proxy export table against the chosen real/system DLL contract.

It must fail if an expected export is missing.

For DXGI, the old proxy must fail this new test because `CreateDXGIFactory2` is missing.

For XInput, verify names **and ordinals**.

Also add a dependency/load test where feasible:

- load the proxy in a small test process;
- resolve every required export;
- call only safe/non-mutating functions;
- prove the real System32 DLL loads and recursion does not occur.

No live GoW install until these tests pass.

## Preserve native Raven authority

Do not rewrite the accepted authority decoder.

The bridge must still provide:

`CompletionistMapGetRavenSnapshotV1`

with atomic all-or-nothing 53-state snapshots.

Do not change save/progression state.

## Runner fixes

Fix:

`tools/v0.10.5/run-raven-authority-bridge-load-proof-and-push.ps1`

Requirements:

- execution-policy-independent invocation instructions should use:
  `pwsh -NoProfile -ExecutionPolicy Bypass -File ...`
- no scalar `.Count` failures;
- detect failed GoW startup cleanly;
- if the process exits immediately or an expected fresh bridge log never appears, treat that as load failure;
- always rollback the owned proxy;
- verify exact pre-run proxy/manifest state;
- verify `version.dll` byte-identical;
- archive/push failure evidence;
- never strand a game-breaking DLL.

Add a regression test that simulates:

- zero log lines;
- one line;
- multiple lines;
- game exits before interaction;
- rollback after failed startup.

## Installer ownership

Keep fail-closed ownership semantics.

If proxy DLL name changes from `dxgi.dll` to `XINPUT1_4.dll`:

- update owner manifest schema carefully;
- preserve upgrade/rollback safety;
- refuse unknown existing DLLs;
- do not overwrite another mod's proxy;
- update recovery tooling.

Never modify `version.dll`.

## Runtime proof acceptance

Only prepare another live test when all offline gates pass.

The next live proof should prove:

- proxy loads;
- real System32 target DLL forwards successfully;
- normal GoW startup succeeds;
- Script Loader still works;
- supported exe hash accepted;
- Raven native snapshot publishes `count=53 unknown=0`;
- rollback restores exact prior proxy state;
- `version.dll` unchanged;
- no save/progression writes.

Do **not** attempt Lua/map delivery yet unless proxy load proof fully passes.

## Deliverables

At minimum push:

1. corrected proxy source/build files;
2. complete export-forwarding definition/generator;
3. export-contract compatibility test;
4. proxy load/resolve test;
5. fixed runner and runner regression test;
6. updated installer/rollback/recovery if DLL target changes;
7. updated `docs/research/v0105-raven-native-bridge.md`;
8. updated handoff.

Success target:

`RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V2_READY`

Meaning:

- old single-export failure cannot recur due to missing public exports;
- offline proxy compatibility gates pass;
- runner scalar bug is fixed/tested;
- one reversible second live proof is ready.

Do not claim `RAVEN_NATIVE_BRIDGE_RUNTIME_READY` yet. Map/Lua delivery remains after successful load proof.

## Repo discipline

After every meaningful stage:

1. commit;
2. push;
3. update handoff when boundary changes;
4. do not stage unrelated user files;
5. no force push;
6. no merge.

If user action is required, stop only after the complete runner is pushed and provide exactly one PowerShell command.
