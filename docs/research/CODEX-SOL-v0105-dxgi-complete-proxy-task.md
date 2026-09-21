# Codex Sol task: compatibility-complete DXGI native bridge

## Branch

Work only on:

`codex/all-ravens-release-candidate`

Do not merge to `main`.
Do not switch branches.
Commit and push every meaningful stage.

## Read first

Mandatory:

- `archive/field-logs/local-handoffs/raven-authority-handoff-20260920.md`
- `docs/research/v0105-raven-native-bridge.md`
- current `native/raven-authority-bridge/`
- current install/rollback/recovery tooling under `tools/v0.10.5/`

Treat the handoff as source of truth.

## Solved — do not redo

Do not redo:

- Raven GameObject codec/carrier;
- 53-Raven identity catalogue;
- staged WAD authority semantics;
- absent-WAD false semantics;
- 53-state native Raven authority decoder;
- atomic snapshot publication;
- save/load/VFS/GetRef/package.loadlib research;
- Script Loader plugin research;
- XInput proxy investigation.

Accepted authority remains:

```text
states=53
explicit=42
absentWadFalse=11
killed=27
alive=26
unknown=0
Veithurgard=false,true,true
```

## XInput route is closed

Successful live targeted import proof:

```text
RAVEN_IMPORT_SLOT ... ordinal=3 ... owner=C:\WINDOWS\SYSTEM32\XINPUT1_4.dll
RAVEN_IMPORT_SLOT ... ordinal=2 ... owner=C:\WINDOWS\SYSTEM32\XINPUT1_4.dll
RAVEN_IMPORT_PROBE_COMPLETE ... owner_consistent=true
```

Evidence:

- `1a6507bd4fd1a5c64e9d31b91b4add0dfafbd97f`
- `archive/field-logs/runtime-captures/gow-xinput-iat-owner-20260921-115740/`

Do not revisit XInput.

## Proven DXGI fact

The earlier game-root `dxgi.dll` was definitely picked up by Windows loader resolution.

The old proxy failed because it exported only:

```text
CreateDXGIFactory1
CompletionistMapGetRavenSnapshotV1
```

and Windows reported:

```text
The procedure entry point CreateDXGIFactory2 could not be located
in the dynamic link library C:\WINDOWS\SYSTEM32\d3d11.dll.
```

This proves DXGI is a viable automatic game-root native load point, but the proxy must be compatibility-complete.

The single-export DXGI proxy is permanently closed. Do not recreate it.

## Mission

Implement a transparent, compatibility-complete `dxgi.dll` proxy suitable for the current Windows/GoW environment while preserving the existing native Raven authority implementation unchanged.

Success target:

`RAVEN_DXGI_COMPLETE_PROXY_LOAD_PROOF_READY`

Do not claim runtime success until a new live proof is performed later.

## Requirements

### 1. Build the real DXGI export contract

Do not use only GoW.exe direct imports.

Determine the complete public export surface of the real target `System32\dxgi.dll`.

Preferred approach:

- inspect the real system DLL export table on the user's machine through a local/offline contract generator, or
- derive a deterministic contract from the supported Windows SDK/system DLL and validate against the user's live System32 DXGI before installation.

Contract must preserve:

- export names;
- ordinals;
- forwarded exports if present.

Store the contract in repo, preferably generated/validated rather than manually guessed.

### 2. Generate transparent forwarding

Implement generated forwarding for the complete contract.

Avoid handwritten wrappers for dozens of functions.

Preferred shape:

- generated `.def` plus architecture-correct thunks, or
- generated named exports that dispatch to the real System32 DXGI by exact name/ordinal.

Requirements:

- preserve calling ABI exactly;
- preserve ordinals exactly;
- never recurse into the local proxy;
- resolve the real DLL from an explicit System32 path;
- fail closed if the real DLL or an expected export is missing;
- do not alter returned DXGI objects/factory semantics.

The proxy may expose the extra Completionist Map snapshot API in addition to the real contract.

### 3. Safe bridge initialization

Do not perform heavy work under loader lock.

If current native Raven authority startup is tied to a forwarded call:

- choose a safe once-only initialization path;
- make it idempotent;
- do not affect the forwarded function result;
- keep Raven authority read-only.

If a minimal `DllMain` is used, keep it trivial.

### 4. Offline export-contract gate

Add a test/tool that compares the built local proxy export table with the real System32 DXGI export contract.

It must fail if:

- a real export name is missing;
- a real ordinal is missing or changed;
- a proxy export collides incorrectly;
- the old single-export proxy is evaluated.

Explicitly prove `CreateDXGIFactory2` is present.

### 5. Load/resolve test

Add a native/offline test process that:

- loads the built proxy from a test directory;
- verifies it loads the real System32 DXGI explicitly;
- resolves every expected contract export from the proxy;
- verifies representative safe factory exports forward successfully where non-destructive;
- verifies no recursion;
- verifies Completionist Map extra snapshot export remains resolvable.

Do not use GoW for this gate.

### 6. Restore installer ownership to DXGI

Update:

- build output;
- installer;
- rollback;
- recovery;
- manifests;
- proof runner;

from `XINPUT1_4.dll` back to `dxgi.dll`.

Requirements:

- schema/version ownership must be explicit;
- refuse unknown existing game-root `dxgi.dll`;
- preserve/restore any recognized previous owned state exactly;
- never overwrite ReShade/another mod/unknown DXGI proxy;
- never touch `version.dll`;
- rollback must be exact on both success and failure.

### 7. Remove dead XInput installation path

The targeted XInput research/probe may stay archived as evidence.

But production install/build logic should no longer target `XINPUT1_4.dll`.

Do not delete historical captures.

### 8. Runtime proof runner V3

Prepare a new reversible runner, but do not require the user to run it until all offline gates pass.

Runner must:

- account for Steam bootstrap exit code 53;
- wait long enough for this machine's ~35-second main-menu startup;
- confirm a fresh DXGI bridge log;
- confirm Script Loader still works;
- require supported GoW exe hash;
- require Raven snapshot `count=53 unknown=0`;
- rollback exact prior DXGI/manifest state;
- verify `version.dll` byte-identical;
- archive and push both pass and failure evidence;
- never strand a broken `dxgi.dll`.

### 9. Preserve Raven authority

Do not rewrite accepted authority code unless required for compilation/integration.

Still no:

- save writes;
- progression writes;
- WriteProcessMemory;
- forced WAD loading;
- SaveGame invocation.

## Windows CI compile gate

The targeted IAT probe already proved that a temporary branch-only GitHub Actions Windows compile gate is useful.

Before asking the user to run the next live DXGI proof:

1. add a temporary Windows CI gate if needed;
2. compile the new DXGI proxy and tests with MSVC warnings-as-errors;
3. run export-contract/load/resolve tests;
4. make CI green;
5. remove the temporary workflow after validation;
6. record the green run in the handoff.

Do not use the user as the compile test.

## Documentation

Update:

- `docs/research/v0105-raven-native-bridge.md`
- `archive/field-logs/local-handoffs/raven-authority-handoff-20260920.md`

Document:

- why XInput is closed;
- exact DXGI export-contract strategy;
- exact compatibility gate;
- installer ownership behavior;
- the single command for V3 proof when ready.

## Stop condition

Stop only when:

```text
RAVEN_DXGI_COMPLETE_PROXY_LOAD_PROOF_READY
```

means:

- complete DXGI contract implemented;
- old CreateDXGIFactory2 failure cannot recur due to missing export;
- offline export parity passes;
- offline load/resolve passes;
- Raven authority tests still pass;
- install/rollback/recovery tests pass;
- Windows CI is green;
- game root is clean;
- one reversible V3 live proof command is ready.

Do not proceed into Lua/map delivery in this pass unless the DXGI load proof has actually passed live in a later step.
