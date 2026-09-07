# Native compass marker registration — v0.10.3

Status: **PARTIAL SUCCESS**. Native data path found and parsed. No new marker registered in running game; no native Raven compass proof claimed.

Branch: `research/v0.10.3-native-compass`, based on clean `b72421c`.
Game executable SHA256: `CAEBCB027980D7EAC9203D190F9EE649EEBC549F8DEFCE138E2114DC91F40452`.
Research date: 2026-09-07. No game launch or live process access. Game files remain unchanged; lookup override prepared under ignored `build/` only.

## What compass targets

`Compass.ShowMarker` accepts a **native map-token name hash**, then an authored **CompassIconClass** name. It does not accept a GameObject or XYZ. Marker identity joins three separate data sets:

1. `exec/dc/pc_le/mapmaster.dcb`: `MAP_PERM_DATA`, type `tMapInfo` (`0x415`). Realms contain regions; regions contain `tMarker` records. These inherit `tMapToken`: `uID`, icon, labels, initial state and flags.
2. `exec/dc/pc_le/mapcoords.dcb`: `MAP_COORDS_PERM_DATA`, type `tMapCoordsInfo` (`0x40A`). Each `tMapCoords` (`0x409`) has matching `uID`, WAD name, position, forward vector, radius controls and in-world marker distance.
3. `exec/dc/pc_le/compassgraph.dcb`: `COMPASS_HELPER_PERM_DATA` (`0x40C`) and `COMPASS_GRAPH_EDGE_PERM_DATA` (`0x40E`). Helpers have their own IDs, WADs, positions and types. Each edge names `firstMarker` and `secondMarker` by hash. Edges reference both map-coordinate IDs and helper IDs.

Native map initialization builds runtime records from mapmaster and joins coordinates by `uID`. Native compass initialization separately loads mapcoords, helpers and graph edges. Moving `Map.CreateMarkerIcon` output therefore moves presentation; it does not register a world target or change this graph.

The stock boat script reads `MapMarkerName` from authored object attributes. That is a reference to a marker identity, not registration. Quest events likewise pass an existing marker hash to MainHUD. `AddMarker` on gameplay objects is also a false lead: stock boat scripts use it for gameplay tags such as `pendingDockCinematic`.

## Native call evidence

Addresses below are **RVAs**, for the executable hash above only. Add actual loaded module base for debugger use. Preferred image base is `0x140000000`. Do not call addresses as guessed C++ functions.

| RVA | Observed operation |
| --- | --- |
| `0x94FF80` | Lua `ShowMarker` wrapper; unboxes name/hash argument |
| `0x94FFF8` | Calls map lookup with marker hash; missing record takes Lua error path |
| `0x95009E` | Validates class through tweak type `0x11E` (`CompassIconClass`) |
| `0x9500DE`–`0x95012A` | Allocates/enqueues request; stores marker hash at request `+0x10`, class hash at `+0x18` |
| `0x2AD490` | Request worker; repeats lookup and dispatches native show |
| `0x760F40` | Map lookup; scans native marker records at stride `0x80`, compares authored `uID` |
| `0x76135E`, `0x76164C` | Map initialization loads `tMapInfo`, then `tMapCoordsInfo` |
| `0x761817` | Compares map marker `uID` with coordinate-record `uID`; matching record supplies position/forward |
| `0x8B0B4E`, `0x8B0BC6`, `0x8B179C` | Compass initialization loads coordinates, helpers, edges |
| `0x6C0C80` | Native show path; tests compass manager lookup at `+0x221E0`, then creates authored UI icon and initializes target position |
| `0x953080` | `Map.GetMarkerInfo`; returns zero Lua results if lookup absent (`0x9530F0`) |

RTTI also identifies `ShowMarkerRequest@...LuaCompass` and `OnWarpResetPathfindingRequest@...LuaCompass`. Stock `boatlevelhelper.lua` toggles named gateways with `SetGatewayMarkerIsOpen`; `cinesequence.lua` calls `OnWarp`. These, plus native graph ingestion, support **engine graph routing**, beyond bearing alone.

Native icon creation and position setup are traced. Exact native distance formula and full route solver remain untraced. `InWorldMarkerDistance` is an observed authored field, not proof of distance-label semantics. No claim that this is general navmesh pathfinding to any arbitrary point. A fresh coordinate without graph integration is insufficient evidence of routing.

Lua-visible Map/Compass binding-name inventories contain lookup, state and icon operations, but no creator/register/coordinate setter. Combined with native initialization code and earlier non-live `Coordinates` assignment, this rules out the proposed simple Map/Compass Lua setter route. It does **not** prove no other hidden binding could ever help. Plain Lua registration remains unestablished; authored DCB input or native plugin is the supported next layer.

## Exact asset evidence

Reader validates all IFF chunk bounds, exports and export hashes, relative pointers and relocation entries. It reads only three small DCB files, no pack extraction.

- 382 map records, 374 unique IDs across all realms.
- Midgard: 65 regions, **318 records**, matching v0.3.1/v0.4 field logs.
- 405 map coordinate records; 1,639 helper records; 3,674 edges.
- Every edge endpoint resolves to map coordinates or a helper: **zero unresolved endpoints**.

DCB layout: 96-byte IFF headers; chunks `0xB` version, `0xC` data, `0xD` exports, `0xE` imports, `0xF` relocations. This build uses field-relative signed 64-bit offsets for pointers inside data, plus relocation-field offsets listed in chunk `0xF`. Export entries specify root offset and type ID. This is enough to inspect/join records; a validated general DCB writer is not shipped.

Key decoded strides: `tMarker=0x48`, `tRegion=0x68`, `tRealm=0x40`, coordinate/helper `0x28`, edge `0x10`. Coordinates and forward components use 16-bit floats. Types and per-field offsets are saved in the engine inventory.

### Previous crash: stronger constraint than unknown hash

v0.7.5 logged successful `ShowMarker(2924516555722838670, "DockPoint")`, then crashed before next probe. This is stock hash `2895F8500B9BD28E`, not an unregistered hash:

- mapmaster record at file `0xD3D8`, icon `goMapIconDock`;
- mapcoords record at file `0x3DF8`, WAD `WAD_Xpl220_FuneralLH`;
- actual native position **(79.5625, -4.0078125, 502.75)**, far from Raven;
- graph neighbours `5ADE904ED5F0A6C6`, `C39E4EE1938E27E3`.

Thus valid map ID + class + graph membership already existed in the failed experiment. They are necessary checks, not a safety guarantee. Queued C++ work explains why `pcall` can succeed before crash. Exact crash cause remains unknown: no usable crash stack found under current game `.crashdata`. Do not repeat the borrowed-ID show call. Possible UI/template/lifecycle interference needs a native stack, not another guess.

## Raven registration path

Reserved name: `Completionist_V103_Veithurgard_Raven_01`.
Hash: `E15E6BC82AE2773E`; no collision in parsed IDs. Keep as hash userdata or name string in Lua, never a double-precision numeric literal.

Actual Raven: **(-64.850898742676, 12.987384796143, 787.30694580078)**.
Authored 16-bit representation: **(-64.875, 12.984375, 787.5)**. Exact live float position therefore needs native runtime support if this quantization is unacceptable.

Nearest existing helper in Raven WAD: `BABC033C454755A0`, position **(-78.5, 12.5546875, 787)**, 13.6594 m away. Graph neighbours are `1A29C3DE478F668A`, `93F48C770603B652`, `BDD71A699CE596F5`. These are candidate attachment points only. Geometric proximity does not prove a reachable route; do not auto-connect by distance.

Concrete proposed implementation, still gated:

1. Create an independent `tMarker` in correct Veithurgard region, new `uID`, non-quest ownership. Preserve every stock marker and array entry. Use separate marker ID for compass, even if current synthetic map visual still borrows a backing ID.
2. Add matching `tMapCoords` with Raven WAD and position. Preserve all stock coordinates. For authored route, rewrite enclosing arrays, counts, relative pointers, relocations and chunk lengths; blind binary append is invalid.
3. Add explicit graph connection from new coordinate ID to a verified reachable helper. Keep all stock edges/gateway semantics. Engine already treats map-coordinate IDs as graph endpoints; an extra helper under the same ID is not established as necessary.
4. Initialize through native loader before map/compass managers build caches, or use native plugin to allocate/register equivalent records with correct lifetimes and ownership. Late Lua tweak-field edits cannot be assumed to rebuild caches.
5. Prove new marker is excluded from progression/save serialization. `tMapToken.InitState` and native state handling mean a discovered authored token is not automatically save-neutral. This gate is unresolved; no DCB patch installed.
6. Resolve independent CompassIconClass/template lifetime. `MAIN`/`SIDE` are quest paths; stock classes include `DockPoint`, `AreaEntrance`, `VendorLocation`, etc. None is declared safe for a new collectible without engine test. No global texture swap needed; Omega stays untouched.
7. Only after native map lookup, coordinate join, compass node and edges pass, enable one user-triggered `ShowMarker`. Record before request, worker execution and subsequent frames. Then test native distance, route bends/gateways, hide, Raven death, reload, and stock marker/Omega regression. Hide only owned Raven ID. Never clear other users' targets.

Most practical next route: **native plugin with read-only probes at initialization and request worker first**, followed by ephemeral registration through that layer. DCB structure is now known enough for a small authored alternative, but save-neutrality and exact target precision need resolution first. Existing GOWTool texpack success does not establish DCB write support.

## Smallest ready diagnostic

Prepared helper only adds read-only logging after existing `MapOn:GetRealmMarkerInfo`. It looks up the reserved name, reports nearby stock baseline entries already returned by engine, and never calls Compass, writes token state, or creates icons. Candidate should report `registered=false` on unchanged game. This is a **baseline/lookup diagnostic**, not registration proof or a test of Add to Compass. It can later verify the same ID after native registration is implemented.

From repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\v0.10.3\lookup-probe.ps1 -Mode Install
```

Launch game yourself; load Veithurgard save; open Midgard map once. No Add to Compass action needed. Close game and export only new diagnostics:

```powershell
Select-String -LiteralPath 'G:\SteamLibrary\steamapps\common\GodOfWar\mods\loader_log.txt' -SimpleMatch '[CompletionistMap v0.10.3]' | ForEach-Object { $_.Line } | Set-Content -Encoding UTF8 .\archive\field-logs\completionist-v103-native-runtime.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\v0.10.3\lookup-probe.ps1 -Mode Remove
```

Installer checks executable hash, then makes unique exact-byte backup and hash manifest under `build/v0.10.3-lookup`. Preserve that directory until rollback. Remove refuses to overwrite newer edits. No boot options, HUD, textures, collectibles or save files patched. Unknown-ID `GetMarkerInfo` null return and name-string unboxing (`0xD36B20`) were checked in executable; `pcall` still cannot catch C++ faults. If startup fails, close game and run Remove.

The next **registration** diagnostic needs a native observer that logs new map entry, matching coordinate node and graph adjacency without showing it or modifying persistent state. The ready Lua baseline cannot inspect compass manager internals; do not treat its success as authorization to call ShowMarker.

## Reproduce and verify

```powershell
python .\tools\v0.10.3\inspect-native-markers.py --output .\archive\field-logs\completionist-v103-native-data.json
python .\tools\v0.10.3\inspect-native-engine.py --output .\archive\field-logs\completionist-v103-native-engine.txt
python .\tools\v0.10.3\test_native_markers.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\v0.10.3\test-lookup-installer.ps1
```

Python tools need Python 3.9+ and standard library only. Engine inventory refuses different executable hash. Disassembly annotations are manually verified anchors, not automatically proven by inventory regeneration. Scratch Capstone/pefile analysis and local source copies stay ignored under `dist/`; no game assets committed.

Validation results and remaining runtime acceptance gates: `archive/field-logs/completionist-v103-validation.txt`.

Sources: local stock `mapmenu.lua`, `mainhud.lua`, `maputil.lua`, `boatdock.lua`, `boatlevelhelper.lua`, `cinesequence.lua`; current overrides; v0.10.1 installer and field result; v0.10.2 tools/logs; v0.6.5.1/v0.7.5/v0.7.6 logs. Native layouts cross-checked against [Nukem9 RTTI definitions](https://github.com/Nukem9/godofwar-gameplay-tweaks/blob/ce73e8ba4f2e077b56249248966901b428ca0fc3/source/Kinetica/RTTI.h) and [IFF header](https://github.com/Nukem9/godofwar-gameplay-tweaks/blob/ce73e8ba4f2e077b56249248966901b428ca0fc3/source/Kinetica/WadChunk.h). [GOWTool WAD reader](https://github.com/kainotoa/GOWTool/blob/42070038b63ba67cc82c2e8c78f2cdae58e51be8/src/Wad.cpp) supplied a second header walk reference. No public tool source found exposing native marker registration.
