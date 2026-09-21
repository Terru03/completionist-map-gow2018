# v0.10.5 Raven native bridge

## Status

The selected release architecture is now a clean-room Windows x64 `XINPUT1_4.dll` proxy. It coexists with the user's upstream `version.dll` Script Loader and never modifies that loader.

The old single-export `dxgi.dll` design is closed after its live loader failure. It must not be installed again. The V2 XInput proxy passes its offline export-contract, safe forwarding, platform, and Raven-authority tests. Installer and runner migration remain before the next live proof.

Native staged-authority read and atomic snapshot publication remain unchanged. Delivery into the existing Lua map remains outside this compatibility-hardening stage.

## Load architecture

The supported `GoW.exe` imports XInput ordinals 2 and 3. The proxy resolves `%SystemRoot%\\System32\\XINPUT1_4.dll` by absolute path, resolves the complete pinned contract once, and uses generated x64 tail thunks to preserve arguments and return semantics. Completionist Map work starts on a separate worker only after a thunk is invoked, outside `DllMain` loader-lock work.

`DllMain` only disables thread attach/detach notifications. Resolution checks each named export by both name and ordinal. Failure routes calls to a non-throwing XInput error stub.

## Proxy architecture comparison

The real System32 contracts on the target machine were inspected, not inferred from `GoW.exe` alone:

| Candidate | Complete system surface | Process-wide risk | Common tooling conflict | Result |
| --- | ---: | --- | --- | --- |
| `dxgi.dll` | 20 named exports | High: `d3d11.dll` and graphics modules bind through it | High: overlays, capture tools, and ReShade commonly use it | Rejected |
| `XINPUT1_4.dll` | 15 exports: 8 named, 7 ordinal-only | Lower: controller API scope | Lower than DXGI; exact ordinal forwarding still required | Selected |

The XInput contract is stored in `native/raven-authority-bridge/xinput1_4-export-contract.json`. A generator emits the `.def`, MASM thunks, and C++ contract header from that one file. The proxy preserves ordinals `1,2,3,4,5,7,8,10,100,101,102,103,104,108,109`; the Raven snapshot API uses ordinal 110.

The mandatory contract test enumerates the real System32 PE export directory and rejects any count, name, ordinal, alias, or missing-proxy mismatch. The load test resolves ordinal 2 and the `XInputGetState` name to the same thunk, calls it, and accepts only `ERROR_SUCCESS` or `ERROR_DEVICE_NOT_CONNECTED`. This gate would reject the old two-export DXGI binary as an XInput proxy.

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

## Compatibility gate

The V2 proxy has no direct dependency on XInput and cannot recurse through its import table. It loads only the absolute System32 target. Its generated forwarding surface contains every export observed on the target Windows build, including all ordinal-only entries. The custom Raven API is the sole extra export.

## Build

From repository root:

```powershell
& .\tools\v0.10.5\build-raven-authority-bridge.ps1 -Clean
```

Generated binaries stay under ignored `build/` and are not committed.

## Install and rollback

The installer requires the exact supported `GoW.exe`, a present `version.dll`, the schema-2 generated build manifest, and a closed game. It refuses any existing `XINPUT1_4.dll` unless an owned manifest names the same target and exact current hash. Upgrade copies both the old DLL and old manifest into the mod-owned backup directory. It never installs the closed single-export `dxgi.dll` design.

Rollback requires the installed DLL hash to match the owned manifest. It restores a prior owned XInput DLL/manifest pair when one exists; otherwise it removes only the known installed pair. Recovery can unwind an owned XInput chain and can remove only the exact known-bad legacy DXGI hash; it refuses unknown proxies. All paths hash `version.dll` before and after and never write it.

```powershell
& .\tools\v0.10.5\install-raven-authority-bridge.ps1
& .\tools\v0.10.5\rollback-raven-authority-bridge.ps1
```

Temp-root regression covers clean install, upgrade backup, chained rollback, unknown-DLL refusal, tampered-DLL refusal, and `version.dll` preservation:

```text
RAVEN_NATIVE_BRIDGE_INSTALL_TESTS_PASSED target=XINPUT1_4.dll clean=true upgrade=true unknown_refused=true tamper_refused=true recovery=true version_untouched=true
```

## One runtime proof command

Run from repository root with God of War closed:

```powershell
git pull --ff-only origin codex/all-ravens-release-candidate; & .\tools\v0.10.5\run-raven-authority-bridge-load-proof-and-push.ps1
```

The runner rebuilds and retests, installs only the owned `dxgi.dll`, launches the game, asks for one advanced-save/map-open pass, extracts fresh bridge lines, rolls back to the exact prior DLL/manifest state, verifies `version.dll` stayed byte-identical, archives evidence, commits it, and pushes this branch.

The pass succeeds only when the log proves System32 proxy load, successful `CreateDXGIFactory1` forwarding, supported exe acceptance, and one atomic snapshot with `count=53 unknown=0`. The expected terminal state is `RAVEN_NATIVE_BRIDGE_LOAD_PROOF_READY`; Lua map delivery remains pending.
