# Codex Sol task: implement clean-room DXGI Raven authority bridge

## Model / usage intent

Use a **long Sol reasoning/coding pass** for this task.

Do not spend the fresh usage window on another broad exploratory scan. The Raven authority problem itself is solved. The remaining job is to build the smallest safe, reversible, testable **delivery architecture** that turns the proven 53-Raven authority into correct in-game map/compass state.

Work continuously until you either:

1. produce a buildable/installable development proof and one exact user test command; or
2. hit one concrete technical blocker that cannot be solved without new runtime evidence, in which case push the complete observer/runner needed for exactly that blocker.

Do not stop after merely writing a design note.

## Branch

Work only on:

`codex/all-ravens-release-candidate`

Do not merge to `main`.
Do not switch to the all-collectibles branch.
Do not rebase or rewrite history.
Commit and push every meaningful stage.

## Read first — mandatory

Start by pulling the branch and reading:

- `archive/field-logs/local-handoffs/raven-authority-handoff-20260920.md`
- the latest `archive/field-logs/source-scans/gow-native-bridge-load-options-*/report.txt`
- `archive/field-logs/source-scans/lua-read-staged-intersections-20260921-092909/report.txt`
- `archive/field-logs/source-scans/staged-owner-reverse-lua-20260921-092551/report.txt`
- the complete Raven acceptance/persistence notes referenced by the handoff
- existing v0.10.5 Raven catalogue/decoder tooling
- current production Raven Lua/map/compass implementation

Treat the handoff as source of truth. Do not redo research marked solved or closed there.

## Product goal

Completionist Map must behave as follows:

- fresh save: all 53 Odin's Ravens appear;
- advanced/old save: only surviving Ravens appear;
- killing a Raven removes that exact Raven immediately;
- opening/reopening the map reconstructs the exact authoritative killed/surviving set;
- preserve current realm, caption, native map marker, and compass fixes;
- no save/progression writes;
- no forced collectible/progression mutation;
- exact identity only; fail closed on unknown state.

## What is already solved — do not redo

The handoff already proves all of the following:

### Raven authority

- catalogue has 53 exact unique Raven identities;
- saved GameObject identity codec/carrier format is solved byte-for-byte;
- staged checkpoint/WAD authority is solved for all 53;
- 42 explicit decoded `ravenKilled` rows plus 11 absent-WAD default-false states are proven;
- `candidate_state_count=53`;
- `unknown_count=0`;
- Veithurgard fixture is exactly `false,true,true`;
- absence-default-false semantics are proven from native WAD lifecycle;
- complete acceptance commit is already recorded in the handoff.

Do not reopen identity, save-codec, absence, or state-semantics research.

### Closed delivery routes

Do not repeat:

- `package.loadlib` — dynamic libraries disabled;
- VFS/VFSExec — command/value registry, not authority bridge;
- `ResolveGameObject`;
- `GetRefBool/GetRefFloat/GetRefInt/GetRefString`;
- `LoadCheck`;
- generic built-in Lua API guessing;
- generic Lua namespace scans;
- old save/load EngineEvent routes;
- selected-slot route as an authority reader.

The reverse native graph found only:

- fixed metadata readers:
  - `GetAppMasterVersion`
  - `GetLevelId`
- write-side:
  - `SaveGame -> 0x66B650 -> 0x6687F0 -> staged serialization`

Do not call `SaveGame` for this mod.

### Script Loader licensing / architecture

The installed Lua Script Loader is Nukem9 `godofwar-gameplay-tweaks` / `version.dll`.

- keep the user's existing upstream `version.dll` untouched;
- upstream exposes no general third-party native plugin ABI;
- upstream README has no redistribution license;
- do not build public Completionist Map around a modified/repackaged Script Loader.

A local fork may be useful only as disposable research evidence, not as the release architecture.

## Newly proven load path

Static import inspection of the exact supported `GoW.exe` proves:

```text
dxgi.dll
  normal import
  exactly one direct GoW import:
    CreateDXGIFactory1

XINPUT1_4.dll
  normal import
  two ordinal imports:
    2
    3

VERSION.dll
  already occupied by Script Loader
```

Primary architecture:

**a separate Completionist Map `dxgi.dll` bridge alongside the untouched `version.dll` Script Loader.**

`XINPUT1_4.dll` is fallback only.

## Exact executable gate

Supported executable SHA-256:

```text
caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452
```

Fail closed on any other `GoW.exe`.

Do not silently use offsets on an unknown binary.

## Core implementation mission

Build a **clean-room, source-controlled native bridge** for this repository that:

1. loads as `dxgi.dll` beside `GoW.exe`;
2. forwards GoW's `CreateDXGIFactory1` call to the real Windows System32 `dxgi.dll`;
3. coexists with the existing upstream `version.dll` Script Loader;
4. initializes Completionist Map outside unsafe loader-lock work;
5. reads only the proven in-process Raven authority;
6. delivers an atomic 53-Raven snapshot to the map/compass implementation;
7. never writes save/progression state;
8. has exact install and rollback tooling;
9. archives proof logs/reports and pushes them.

This should be a real buildable development proof, not pseudocode.

## DXGI proxy requirements

Implement the proxy conservatively.

At minimum:

- export `CreateDXGIFactory1` with the exact Windows ABI;
- load the real system DXGI by an absolute System32 path or an equivalently recursion-safe System32-only mechanism;
- never resolve the proxy itself recursively;
- forward the original call transparently;
- preserve HRESULT/output semantics;
- fail cleanly if the real export cannot be resolved;
- keep `DllMain` minimal;
- do meaningful initialization from the first forwarded export call or a safe worker started outside loader-lock;
- call `DisableThreadLibraryCalls` if appropriate.

For the first proof, matching the one symbol GoW directly imports is sufficient.

But document the compatibility caveat: a public release may need broader DXGI export forwarding for third-party overlays/ReShade/mod stacks that resolve extra DXGI exports dynamically.

Do not overwrite or modify the user's `version.dll`.

## Raven authority reader

Do **not** invent another save reader.

Port/reuse the already-proven staged authority logic from the repository.

The native bridge must derive the same 53-state result as the accepted v0.10.5 tooling.

Important proven native structures are documented in the handoff, including the staged record table and WAD binding lifecycle. Reuse those exact facts and the existing decoder/catalogue sources rather than re-deriving them.

Requirements:

- validate module base and supported exe hash;
- bounds-check every pointer/count/length;
- never trust malformed runtime structures;
- exact Raven identity matching only;
- produce an all-or-nothing snapshot object:
  - 53 catalogue IDs;
  - exact alive/killed bool for each;
  - generation/timestamp counter for internal synchronization;
  - diagnostic reason if snapshot is rejected.

The map layer must never see a partially updated 53-state table.

## Delivery to the mod — preferred order

The bridge exists because ordinary Lua cannot read the staged authority directly. Solve delivery in this order.

### Preferred A — legitimate in-process Lua API registration/call

If repository evidence is sufficient to obtain the active game Lua state and call the game's existing Lua C API safely, register one small read-only namespace/function, for example conceptually:

`CompletionistMapNative.GetRavenSnapshot()`

Requirements:

- use legitimate Lua API/native registration calls rather than raw byte patching if possible;
- do not overwrite an existing engine binding;
- expose read-only snapshot data only;
- no save/progression mutation functions;
- make registration idempotent;
- survive map reopen/load transitions;
- preserve the existing immediate loaded-Raven `ravenKilled` Lua event path.

Do not revive `package.loadlib`; that path is closed.

### Preferred B — native map synchronization

If safe Lua registration cannot be completed without brittle engine-code patching, keep the bridge independent of Lua and synchronize the Raven map/compass state natively using already-proven game marker functions/data.

If choosing this route:

- reuse the current 53 Raven catalogue/positions/realm metadata;
- preserve the known-good marker classes/artwork;
- update only Completionist Map marker presentation;
- do not touch collectible progression;
- do not force-load Raven WADs;
- map-open/load must rebuild all 53 states atomically;
- immediate kills must still remove the exact Raven promptly, either through a proven event signal or a safe state refresh.

### Do not use as delivery

Do not use:

- save-file rewrites;
- `SaveGame`;
- progression writes;
- VFSSet*;
- external physical-save polling as authority;
- broad process memory scans;
- `WriteProcessMemory`;
- arbitrary executable byte patches just to create a bridge;
- a modified upstream Script Loader binary.

If one tiny in-process hook becomes absolutely necessary, stop and prove why first. Keep it isolated, reversible, version-gated, and never conflate it with save/progression mutation.

## Safety boundary

Allowed:

- a native DLL intentionally loaded by GoW as `dxgi.dll`;
- in-process read access to GoW's own memory;
- legitimate calls to Windows APIs;
- legitimate read-only/native UI integration necessary for the mod;
- writing Completionist Map's own diagnostic log/config under its mod-owned path;
- reversible install/rollback of Completionist Map-owned files.

Forbidden:

- save writes;
- progression writes;
- collectible state mutation;
- `WriteProcessMemory`;
- force-loading Raven WADs;
- invoking `SaveGame`;
- overwriting unknown user files without hash/backup gates;
- modifying `version.dll`;
- redistributing proprietary game binaries;
- committing generated/proprietary binaries if repository policy excludes them.

## Build system

Prefer a small reproducible Windows x64 build under a new source directory such as:

`native/raven-authority-bridge/`

Use whichever of CMake/MSBuild is already most appropriate for the user's installed Windows toolchain, but keep it easy to reproduce.

Commit:

- source;
- project/build files;
- export definition if used;
- tests that can run offline;
- build/install/rollback scripts;
- documentation.

Do not commit the generated `dxgi.dll` if the repository's binary policy says not to. Build it locally from source.

## Install / rollback discipline

Create fail-closed tooling under `tools/v0.10.5/`.

Installer requirements:

- GoW must be closed;
- verify exact `GoW.exe` SHA-256;
- verify current `version.dll` is left untouched;
- refuse to overwrite an existing `dxgi.dll` unless it is a previously installed Completionist Map bridge with a recognized manifest/hash;
- back up any file that is intentionally replaced;
- write a manifest containing exact hashes;
- install only Completionist Map-owned files.

Rollback requirements:

- verify manifest/hash before removal/restoration;
- never delete an unknown user's `dxgi.dll`;
- leave `version.dll` untouched;
- leave saves/progression untouched.

## Development proof logging

The bridge should emit a concise diagnostic log sufficient to prove:

- proxy loaded;
- real System32 DXGI resolved;
- `CreateDXGIFactory1` forwarded successfully;
- supported GoW exe hash accepted;
- bridge initialization succeeded;
- Raven authority snapshot count=53;
- unknown count=0;
- alive/killed counts;
- selected delivery mechanism initialized;
- map-open snapshot refresh occurred;
- exact Raven removal occurred when a Raven is killed, if tested;
- no save/progression write path was invoked by the bridge.

Do not log huge raw memory dumps.

## Offline tests

Before asking David to run GoW, add offline/unit tests for as much as possible:

- DXGI path/forwarder resolution helper;
- supported-exe gate;
- Raven catalogue uniqueness=53;
- snapshot atomicity;
- exact decoder fixtures already in repository;
- Veithurgard `false,true,true`;
- absent-WAD default-false semantics;
- manifest/install/rollback validation logic.

Reuse existing fixtures rather than duplicating large binaries.

## User runtime test

Do not run God of War yourself.

When the development proof is ready:

1. push everything;
2. update the mandatory handoff;
3. provide **exactly one PowerShell command** that:
   - pulls this branch;
   - builds the bridge;
   - installs it with fail-closed checks;
   - launches GoW only if the repository's established test runner already does so safely, otherwise installs and instructs the user to launch manually;
   - captures the bridge log/result;
   - restores/rolls back automatically if the test design requires that;
   - commits/pushes the resulting evidence.

Prefer one runner that produces all evidence needed for the next decision.

## Required deliverables

Push meaningful work continuously.

At minimum, aim to produce:

1. `native/raven-authority-bridge/`
   - clean-room DXGI proxy source;
   - Raven authority reader;
   - chosen delivery implementation;
   - reproducible build files.

2. `tools/v0.10.5/build-raven-authority-bridge.ps1`

3. `tools/v0.10.5/install-raven-authority-bridge.ps1`

4. `tools/v0.10.5/rollback-raven-authority-bridge.ps1`

5. one runtime proof runner that archives/pushes evidence.

6. `docs/research/v0105-raven-native-bridge.md`
   - architecture;
   - exact safety model;
   - coexistence with Script Loader;
   - supported exe hash;
   - public-release compatibility caveats;
   - current proof status.

7. update:
   `archive/field-logs/local-handoffs/raven-authority-handoff-20260920.md`

## Success states

Best outcome:

`RAVEN_NATIVE_BRIDGE_RUNTIME_READY`

Meaning:

- clean-room `dxgi.dll` proxy builds;
- real DXGI forwarding is correct;
- upstream `version.dll` remains untouched;
- supported exe gate works;
- 53-state authority snapshot works;
- map/compass consumes it;
- no save/progression writes;
- one reversible user runtime test is ready.

Acceptable intermediate outcome:

`RAVEN_NATIVE_BRIDGE_LOAD_PROOF_READY`

Meaning:

- proxy/load/build/install/rollback are complete;
- authority reader is implemented or wired;
- one exact unresolved delivery boundary remains;
- a single targeted user test can settle it.

Not success:

- another broad xref report;
- another speculative Lua namespace search;
- another save parser;
- another `package.loadlib` attempt;
- a modified Script Loader binary;
- a design note without buildable source;
- stopping after the first small commit.

## Repo discipline — mandatory

After every meaningful stage:

1. commit;
2. push to `codex/all-ravens-release-candidate`;
3. update the handoff when the architectural boundary changes;
4. do not stage unrelated files;
5. no force push;
6. no merge.

If a runtime test becomes necessary, stop only after the complete runner is pushed and give David exactly one PowerShell command.
