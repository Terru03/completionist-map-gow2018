# v0.10.5 Raven native bridge

## Status

The selected release architecture is a clean-room Windows x64 `dxgi.dll` proxy. It coexists with the user's upstream `version.dll` Script Loader and never modifies that loader.

Current implementation stage: DXGI forwarding and native staged-authority reader are buildable and pass the accepted archived replay. Delivery into the existing Lua map remains open.

## Load architecture

The supported `GoW.exe` imports one DXGI symbol: `CreateDXGIFactory1`. The proxy resolves `%SystemRoot%\\System32\\dxgi.dll` by absolute path, resolves that export once, forwards the original arguments and return value, then starts Completionist Map initialization from the forwarded call path outside `DllMain` loader-lock work.

`DllMain` only disables thread attach/detach notifications. Failure to load the system DLL or its export returns a failing `HRESULT` and clears the output pointer.

## Safety model

- Supported `GoW.exe` SHA-256: `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`.
- Raven authority reads will be in-process and read-only.
- No save, progression, quest, collectible, or executable bytes are written.
- The bridge never calls `SaveGame` and never force-loads a WAD.
- Bridge diagnostics live under `mods/completionist-map/native/`.
- Install and rollback must be manifest/hash gated and must leave `version.dll` untouched.

## Raven authority reader

The bridge ports the accepted Channel-A logic without opening a save file:

- exact supported-executable hash gate;
- proven staged globals at `0x22C6938`, `0x22C6940`, `0x22C696C`, and `0x22C7170`;
- two equal bounded table/pool reads before decode;
- native cached Lua length framing;
- bounded MSB-first bit-phase search;
- zlib carrier decode using upstream zlib `v1.3.1` pinned to commit `925af44f3cde53c6b076611c297850091b5dc7bb`;
- exact 53-entry `(registry_hash, object_hash)` matching;
- native absent-WAD default-false rule;
- all-or-nothing 53-state publication through `CompletionistMapGetRavenSnapshotV1`.

The worker publishes only a complete snapshot. Present WAD plus missing, conflicting, ambiguous, malformed, changing, or out-of-bounds state rejects the whole candidate. The bridge never exposes a partial table.

Offline replay of the accepted 425-record capture passes with:

```text
RAVEN_BRIDGE_AUTHORITY_TESTS_PASSED states=53 explicit=42 absentWadFalse=11 killed=27 alive=26
```

The test also proves the Veithurgard `false,true,true` fixture and stresses atomic snapshot publication between all-alive and all-killed vectors.

## Open delivery boundary

The bridge currently exposes a read-only native snapshot API. The existing Lua map cannot call it yet because `package.loadlib` and all direct built-in authority bindings are closed. No engine bytes are patched. Until a legitimate Lua registration/call boundary or native marker synchronization is proven, this is a load-proof architecture, not runtime-ready map delivery.

## Compatibility caveat

The development proof forwards the only DXGI export directly imported by the supported `GoW.exe`. A public release may need a broader forwarding surface for overlays, ReShade, or other mod stacks that dynamically resolve extra DXGI exports. Such compatibility work must remain separate from Raven authority and must not replace unknown user files.

## Build

From repository root:

```powershell
& .\tools\v0.10.5\build-raven-authority-bridge.ps1 -Clean
```

Generated binaries stay under ignored `build/` and are not committed.

## Install and rollback

The installer requires the exact supported `GoW.exe`, a present `version.dll`, the generated build manifest, and a closed game. It refuses any existing `dxgi.dll` unless an owned manifest names the same target and exact current hash. Upgrade copies both the old DLL and old manifest into the mod-owned backup directory.

Rollback requires the installed DLL hash to match the owned manifest. It restores a prior owned DLL/manifest pair when one exists; otherwise it removes only the known installed DLL and manifest. Both paths hash `version.dll` before and after and never write it.

```powershell
& .\tools\v0.10.5\install-raven-authority-bridge.ps1
& .\tools\v0.10.5\rollback-raven-authority-bridge.ps1
```

Temp-root regression covers clean install, upgrade backup, chained rollback, unknown-DLL refusal, tampered-DLL refusal, and `version.dll` preservation:

```text
RAVEN_NATIVE_BRIDGE_INSTALL_TESTS_PASSED clean=true upgrade=true unknown_refused=true tamper_refused=true version_untouched=true
```
