# v0.10.5 Raven native bridge

## Status

The selected native load architecture is a clean-room Windows x64 **compatibility-complete `dxgi.dll` proxy**.

The XInput proxy route is closed by live evidence: both normal GoW XInput import slots resolve to `C:\Windows\System32\XINPUT1_4.dll` on the target machine, while a game-root XInput proxy produced no bridge startup evidence.

The original single-export DXGI proxy is also closed. Its live loader failure was caused by an incomplete export surface: `d3d11.dll` required `CreateDXGIFactory2`, which that proxy did not export.

The replacement DXGI proxy now implements the complete 20-export System32 contract observed on the target Windows build, preserves names and ordinals, forwards to the explicit System32 DLL, exposes the Raven snapshot API as the sole extra export, and passes native parity/load tests.

Current boundary:

```text
RAVEN_DXGI_LOCAL_OFFLINE_GATE_READY
```

A local temp-root install/rollback/recovery gate must pass before the V3 live proof is run.

## DXGI export contract

Pinned target System32 `dxgi.dll` SHA-256:

```text
b12aebf0f077d6c1394b50e2eecdd5e16072c9a0c871f30887b5d170cbf2eaae
```

The observed surface is 20 named exports with ordinals 1 through 20. `CreateDXGIFactory2` is ordinal 12.

The contract is stored in:

`native/raven-authority-bridge/dxgi-export-contract.json`

A generator emits:

- the proxy `.def`;
- x64 MASM forwarding thunks;
- a C++ contract header.

The generated proxy preserves the full real contract. `CompletionistMapGetRavenSnapshotV1` is the sole extra export at ordinal 21.

## Forwarding design

The proxy loads the real DXGI only from the explicit System32 path and validates every expected export by both name and ordinal before forwarding.

Forwarding is implemented with generated tail thunks so arguments, stack state, return values, and ABI semantics remain transparent.

`DllMain` performs no heavy bridge work. It only disables thread attach/detach notifications.

The Raven authority worker starts once, after a forwarded DXGI call is successfully resolved, and runs outside loader lock.

## Offline native compatibility gate

The native suite contains five CTest targets:

1. platform tests;
2. complete DXGI forwarding/load tests;
3. export-contract parity tests;
4. explicit rejection of an intentionally incomplete DXGI fixture;
5. Raven authority replay/atomic snapshot tests.

The forwarding test copies the built proxy into a temporary directory, loads it there, proves the real System32 DXGI is also loaded without recursion, resolves every contract name/ordinal, resolves the Raven snapshot API, and safely calls:

- `CreateDXGIFactory`;
- `CreateDXGIFactory1`;
- `CreateDXGIFactory2`.

The export-contract test compares the complete built surface to the real System32 DXGI and explicitly requires `CreateDXGIFactory2`.

The old-style incomplete proxy fixture is rejected by test.

## Windows CI gate

Temporary GitHub Actions workflow run:

`35600350597`

completed successfully.

Verified on the hosted Windows x64 runner:

```text
RAVEN_DXGI_POWERSHELL_PARSE_PASSED files=9
100% tests passed out of 5
RAVEN_NATIVE_BRIDGE_RUNNER_TESTS_PASSED target=dxgi.dll ...
RAVEN_DXGI_SECURITY_DIFF_SCAN_PASSED files=21 findings=0
```

The temporary workflow was removed after the green run.

The build script supports both Visual Studio 2022 and Visual Studio 2026 CMake generators.

## Safety model

- Supported `GoW.exe` SHA-256:
  `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`.
- Raven authority is read-only in process.
- No `WriteProcessMemory`.
- No save/progression writes.
- No `VFSSetFloat` / `VFSSetInt`.
- No `SaveGame` invocation.
- No forced WAD loading.
- No executable-byte patching.
- Existing upstream `version.dll` Script Loader remains untouched.
- Bridge diagnostics are written only under `mods/completionist-map/native/`.

The DXGI-task security diff scan checked 21 changed native/tool files and found zero references to the prohibited process-injection/progression-write API set.

## Raven authority reader

The accepted 53-state authority implementation is unchanged.

It uses:

- exact supported-executable hash gate;
- proven staged globals;
- two equal bounded staged snapshots;
- bounded Channel-A carrier decode;
- exact 53-entry Raven identity mapping;
- authoritative absent-WAD default false;
- atomic all-or-nothing snapshot publication.

Accepted fixture:

```text
states=53
explicit=42
absentWadFalse=11
killed=27
alive=26
unknown=0
Veithurgard=false,true,true
```

The native API remains:

`CompletionistMapGetRavenSnapshotV1`

## Schema-3 install ownership

Production native target:

`dxgi.dll`

Build/install manifest schema:

`3`

Proxy contract marker:

`system32-dxgi-v1`

The installer:

- requires the supported GoW hash;
- requires the schema-3 build manifest;
- refuses any existing game-root `dxgi.dll` unless the matching manifest proves it is an exact owned Completionist Map bridge;
- never overwrites unknown DXGI/ReShade/other proxies;
- stages copies before replacement;
- backs up the previous owned DLL and manifest during upgrade;
- verifies hashes after installation;
- verifies `version.dll` is byte-identical.

Rollback:

- refuses a tampered installed bridge;
- restores an exact previous owned schema-3 pair through a staged DLL copy;
- otherwise removes only the exact owned pair;
- preserves `version.dll`.

Recovery:

- unwinds schema-3 owned DXGI chains;
- can remove only the exact historical known-bad single-export DXGI hash;
- refuses unknown/unowned game-root DXGI files;
- does not use the closed XInput production path.

## Local offline gate

Before a live proxy install, run:

`tools/v0.10.5/test-raven-authority-bridge-offline-gates.ps1`

This performs:

1. runner regressions;
2. clean native build + all five CTest targets;
3. schema-3 install/upgrade/rollback/recovery tests in a **temporary directory** populated with copies of the real `GoW.exe` and `version.dll`.

It does not install a proxy into the real game directory.

Success marker:

```text
RAVEN_DXGI_OFFLINE_GATES_PASSED
```

## V3 live proof

Prepared runner:

`tools/v0.10.5/run-raven-authority-bridge-load-proof-and-push.ps1`

V3:

- uses `dxgi.dll`;
- allows 90 seconds for Steam bootstrap/handoff/startup;
- waits an additional 40-second main-menu settle interval;
- requires fresh DXGI proxy load/forwarding/executable-acceptance evidence before prompting;
- asks for one advanced-save/map-open pass;
- requires `count=53 unknown=0`;
- requires normal Completionist Map Script Loader evidence;
- rolls back the exact pre-run DXGI/manifest state;
- verifies `version.dll` byte-identical;
- stops GoW before failure rollback;
- archives and pushes both success and failure evidence.

Do not run V3 until the local offline gate passes.

## Post-load boundary

After a successful V3 load proof, the remaining problem is delivery of the accepted native 53-state snapshot into the existing map/compass runtime.

Preferred next direction remains legitimate in-process Lua registration or another non-progression-mutating native marker-sync boundary.

Do not redo Raven authority research.
