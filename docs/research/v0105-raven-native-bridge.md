# v0.10.5 Raven native bridge

## Status

The selected release architecture is a clean-room Windows x64 `dxgi.dll` proxy. It coexists with the user's upstream `version.dll` Script Loader and never modifies that loader.

Current implementation stage: DXGI forwarding build proof. Raven staged-authority decoding and delivery are still being added.

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

## Compatibility caveat

The development proof forwards the only DXGI export directly imported by the supported `GoW.exe`. A public release may need a broader forwarding surface for overlays, ReShade, or other mod stacks that dynamically resolve extra DXGI exports. Such compatibility work must remain separate from Raven authority and must not replace unknown user files.

## Build

From repository root:

```powershell
& .\tools\v0.10.5\build-raven-authority-bridge.ps1 -Clean
```

Generated binaries stay under ignored `build/` and are not committed.
