# Raven HUD physical grammar proof — v3 stop

Work uses `codex/v104-raven-hud-research`, pulled from `b868f19`. Authoritative task stays unchanged: [ASTRA task](ASTRA-v104-raven-hud-clone-task.md).

**WAD gate blocked. Raven HUD clone not ready for runtime test. No WAD or DCB candidate built.**

Task says: “If the evidence shows the three-payload design itself is structurally invalid, stop and report the actual required topology instead of forcing these acceptance criteria.” This clause applies to preserving complete source groups while demanding exactly +3 payloads / +2 accounting. Source groups need +4 / +3. This does not prove every possible three-payload design impossible; script-sharing semantics remain unproven.

## Source and peer proof

Read only `G:\SteamLibrary\steamapps\common\GodOfWar\exec\wad\pc_le\r_ui.wad`.

SHA256: `9eb1f548de036eb56c031561a9b7665d71b54fe251d360d2a5b7c60e3d6ff3c3`.

Pinned parser helper hash passes. Source parse/serialize byte exact: 53,811 physical records; 20,415 nonempty payload records. Reserved Raven names and IDs have no record-header collisions.

Inspector uses archived reduced class report to locate all root, prototype, and model groups for DockPoint, FastTravel, Valkyrie, MAIN, and SIDE. It checks source index/name/ID against that report. All 15 groups have matching role/kind/depth/flags/data-size/type layouts per resource role. Their generic boundary records match byte for byte across peers. All five prototype SCP bodies also match byte for byte.

## Physical grammar

Each physical record has 96-byte header, declared data bytes, then padding to 16-byte boundary. Parser keeps header and padding bytes. Kind 2 opens group; kind 3 closes it; kind 1 holds resource definition or zero-data link. Role comes from kind, stack scope, flags, data presence, target position, and peer shape. Name equality does not define role.

Dock spans below include both boundaries. All three groups top-level; direct members have parent equal to group start. Inspector depth uses 0 for outer start/end and 1 for direct members. End record's stored parent still points to group start.

| Role | Absolute records | Complete physical order | Nonempty payloads |
|---|---|---|---:|
| Model | 49145–49149 | `GroupStart`, `MDL_boatdock`, material link, mesh link, `GroupEnd` | 1 |
| Prototype | 49150–49154 | `GroupStart`, `goProtoBoatDock`, model link, **`SCP_BoatDock`**, `GroupEnd` | **2** |
| Root | 49155–49157 | `GroupStart`, `goboatdock`, `GroupEnd` | 1 |

Boundary names are generic `GroupStart` / `GroupEnd`, flags 0, no data. Start ID is `aaaaaabaaaaaaaaaaaaaaaaa95d3aaaa`; end ID is `aaaaaabaaaaaaaaaaaaaaaaa03d4aaaa`. Neither ID is resource identity. Preserve both records byte exact, including opaque header tail.

Definitions and links:

| Record | Kind / flags | Data bytes | Role / dependency representation |
|---:|---|---:|---|
| 49146 | 1 / `0x8E` | 80 | Model payload, type `0x1002000C` |
| 49147 | 1 / `0` | 0 | Local link to `MAT_0C599DC8DC7E2170` |
| 49148 | 1 / `0` | 0 | Local link to `MG_boatdock_0` |
| 49151 | 1 / `0x3D` | 1184 | Prototype payload, type `0x10001` |
| 49152 | 1 / `0` | 0 | Local link to `MDL_boatdock` |
| 49153 | 1 / `0x18` | **96** | Local SCP payload, type **`0x10005`**, begins with script class `SCR_UI` |
| 49156 | 1 / `0x3D` | 164 | Root payload, type `0x20001` |

No inline model ID occurs in prototype payload. No inline material or mesh ID occurs in model payload. Each uses exactly one local link in slot shown above. Root has inline prototype ID at `+0x0C` and shared compass ID at `+0x54`, with no physical dependency-link records.

## Intentional clone edits and preserved bytes

New helper copies complete group. It changes only selected target definition and explicit local slots. Nested records that share name/ID stay unchanged; unsupported HUD nesting fails strict shape validation.

1. **Model:** change target header name/ID to `MDL_completionistravenhud` / `4a7911dc2db72cecaf6c187a66bfd11f`. Change only direct material link name/ID to `MAT_AE4AD85BB993F040` / `dac6009fd0f18caad2ed322463c3d0c8`. Keep model body, mesh link, wrappers, flags, padding, and opaque bytes exact.
2. **Prototype:** change target header name/ID to `goProtoCompletionistRavenHUD` / `b2a833d6144789e8099acf85e832d652`. Retarget direct model link. Change self-ID at `+0x3A8`, located by ID-table pointer at `+0x18`; peer node count is 2. Preserve other node IDs, node names (`BoatDock`, `Next`), authored data, and **whole local SCP record**. Its exact binding semantics remain open; no unsupported renaming or conversion.
3. **Root:** change header name/ID to `gocompletionistravenhud` / `f0029a68d9705e95a981aab8bff0c5b8`. Set `+0x0C` to new prototype ID. Set 56-byte loader name field `+0x1C..+0x53` to new WAD spelling with NUL padding. Preserve `+0x54` shared compass ID `502b9225361cf6449d8d85048f0b1a75` and every other byte.

V3 tests these three complete group edits **in memory**. Each serializes, reparses, and round-trips byte exact. Undoing only listed edits restores each source group byte for byte. Entire parsed source also serializes back to original WAD after preview. This proves transform isolation, not full candidate acceptance or engine loading.

## Why both prior builders fail

- **V1:** assumes prototype→model and model→material/mesh IDs occur inline. Actual source stores them as zero-data local records. Reproduced `ValueError: Dock prototype model reference count changed` on pinned WAD.
- **V2:** detects dependency signature but calls v1 `clone_group()`, which demands two records named like definition. Real wrappers generic; only target carries resource name. Reproduced `ValueError: MDL_boatdock: group did not contain wrapper + payload names`.
- Lowering rename assertion still fails deeper contract: copying whole prototype also copies nonempty SCP payload. Both versions also leave prototype self-ID and root payload loader name stale. V3 exposes these issues instead of declaring a full candidate ready.

## Why script cannot silently become link

`SCP_BoatDock` ID `baaddbbad0baaddbbaaddbbad7baaddb` appears on **2,057 payload definitions with 211 distinct byte contents**; only 401 bodies match Dock SCP. ID-only lookup cannot identify one script or even one equivalent body.

Pinned WAD has just three zero-data links using this sentinel ID: records 32442–32444, `SCP_MapIconDock`, `SCP_CollidableSphere9`, `SCP_flourishD1`. Those belong to inserted working Raven map chain. Existing map builder converted these from local definitions. That success is evidence for that map path, not proof that HUD script local binding can be removed. Stock compass peers keep their root-node SCP bodies. Stock glyph SCP links use other, distinct resource IDs.

Possible next research: trace how loader binds local SCP records to prototype nodes, including sentinel IDs and name/scope matching. Then prove a safe share path or revise design to keep local fourth payload. Do not guess by clearing SCP data, redefining “payload,” or changing only arithmetic assertions.

## Actual counts if complete groups cloned

| Gate | Source | Complete clone | Task requires |
|---|---:|---:|---:|
| Physical records | 53811 | 53824 (+13) | Real topology delta |
| Payload records | 20415 | **20419 (+4)** | 20418 (+3) |
| WAD_R_UI total | 16802 | **16805 (+3)** | 16804 (+2) |
| `0x10001` | 1725 | 1726 | 1726 |
| `0x20001` | 2073 | 2074 | 2074 |
| `0x10005` | 2600 | **2601** | 2600 |

Source type rows equal measured populations for all three affected types. Model type is outside root table. Above “complete clone” column is derived arithmetic, **not a written WAD candidate**. No accounting bytes changed. Four-payload full WAD serialization, loader order, DCB linkage, and runtime validity remain untested.

## Deliverables and verification

- Role/clone module: `tools/v0.10.4/compass_hud_physical_groups.py`.
- Read-only inspector and runner: `tools/v0.10.4/inspect-compass-hud-physical-groups.py` / `.ps1`.
- V3 blocked preflight: `tools/v0.10.4/build-raven-compass-hud-three-payload-v3.py`; active `build-raven-compass-hud-three-payload.ps1` now selects v3. No recursive cleanup, implicit commits, or push in runner. V1/v2 Python files unchanged as history.
- Tests: `tools/v0.10.4/test_compass_hud_physical_groups.py`.
- Physical proof: `archive/field-logs/completionist-v104-compass-hud-physical-groups.json`.
- Gate/clone-preview proof: `archive/field-logs/completionist-v104-raven-compass-hud-three-payload-v3.json`.

Fresh verification at this revision: 36 tests pass via `python -m unittest discover -s tools/v0.10.4 -p "test_*.py" -v` (19 new focused tests, 17 existing). Initial focused tests failed before implementation. Inspector runs on real pinned WAD and exits 0. Active v3 runner runs on same WAD and exits **3**, expected structural block. No full WAD build passed. No DCB work started. No candidate file or candidate hash exists.

No game launch, game writes, DCB writes, save/progression/marker changes. WAD source remains pinned hash after verification.

Exact next PowerShell command, from any current directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\david\Documents\GitHub\completionist-map-gow2018\tools\v0.10.4\build-raven-compass-hud-three-payload.ps1"
```

This reruns read-only proof and writes repo JSON reports. Expect exit 3 and `OFFLINE_RAVEN_COMPASS_HUD_THREE_PAYLOAD_BLOCKED`. **Not safe to install candidate or launch God of War for Raven HUD test yet.** Existing live game state was left untouched.
