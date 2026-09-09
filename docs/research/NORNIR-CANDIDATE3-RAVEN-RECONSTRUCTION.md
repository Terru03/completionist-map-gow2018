# Raven reconstruction and offline Nornir Candidate 3

## Result

Raven recipe is now clear enough to build one offline candidate. Working Raven does **not** have a dedicated map model group or HUD model group. It shares `MG_mapicondock_0` on map path and `MG_boatdock_0` on HUD path. Custom art stays local because dedicated Raven models bind dedicated Raven material through model-owned dependency rows. Raven material then owns Raven diffuse and emissive links.

Failed Nornir path first split from this recipe in material payload, before any model-group work. Raven history proved this rule:

- clone Dock material;
- give clone fresh resource ID;
- give clone fresh `+0x10` qword;
- preserve Dock donor `+0x20 = D595197B0961F689`;
- retarget only diffuse and emissive links.

Commit `c4b7270` instead gave Nornir fresh values at both `+0x10` and `+0x20`. Failed Candidate 1 used `+0x20 = E2265134DFA7B641`. Candidate 2 kept that first split, then cloned both stock MG payloads under new names and IDs. Runtime still made stock boat docks show Nornir art, hid Raven map art, and crashed. Thus dedicated MG clone was not Raven recipe and did not fix first known split.

Candidate 3 starts from frozen Raven files. It keeps shared stock MG definitions and restores Nornir material `+0x20` to Raven-proven donor value. It changes no opaque MG byte. Against failed Candidate 1, new WAD differs by exactly one contiguous 8-byte field. This is historical reconstruction, not claim that exact engine meaning of `+0x20` is decoded.

Candidate stays offline. Runtime install is not allowed.

## History used

| Stage | Key commits | Proof or meaning |
| --- | --- | --- |
| Last clean UI base | `ec23e80`, `9ddb1dc` | Stock/pre-custom `r_ui.wad` `92294d...`; prove material `+0x10` unique and `+0x20` shareable; select fresh `+0x10` plus preserved donor `+0x20`. |
| First custom Raven map art | `694f2f0`, `a91b021`, `362233c`, `72ba3e9` | Build dedicated map material/model/prototype/root; runtime capture shows Raven map visual active, clickable, native placed. |
| Corrected map production chain | `ff2d6dc`, `5298a14`, `cfb07eb`, `79570b3`, `b463eaa` | Fix WAD type accounting and embedded root loader name. Then prove resident Raven art. Final pre-HUD WAD becomes `9eb1f548...`. |
| HUD resource discovery | `a775cf9`, `53ad400`, `1c06a6c`, `fecb4d8`, `2dcc68e` | Prove `DockPoint.IconName` resolves to `goboatdock`, not map root. Prove Raven material can be reused with stock `MG_boatdock_0`. |
| HUD construction and success | `16cc157`, `4309ba8`, `78da41d`, `beb86a9`, `d13da33`, `00564d4` | Build four-payload HUD chain, bind class `IconName`, register GOPool row, then prove custom Raven HUD, native distance/path, and single-target Add/Replace/Remove. |
| In-world art | `df53bf8`, `76cfa75`, `092f153`, `d420590`, `c1551a2` | Clone type-`0x129` carrier. Stock-art control proves export resolves. Capacity 1 blocks second custom instance; capacity 2 gives HUD plus in-world Raven. |
| Production freeze | `5108330` | Adopt verifier, hashes, schema, and final architecture. |

Some older reports show blocked or failed ideas. They are not final recipe. Direct map proof WAD `d33d623d...` proved first visual success, but corrected production chain is `e4a56165...` then resident-art `9eb1f548...` then final HUD WAD `5d7cb320...`.

## Raven transformation ledger

Machine form lives in `archive/field-logs/completionist-v104-nornir-candidate3-offline-reconstruction.json`.

### `exec/wad/pc_le/r_ui.wad`

Baseline: `92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04`

Production: `5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60`

Map path:

| Resource | ID or hash | Donor and exact change | Physical owner |
| --- | --- | --- | --- |
| `TX_completionist_raven_map_diffuse_19A41F00834C19F3` | def `5458455400455255001fa419f3194c83`; GPU `000000000000000079babb7a41c7033c`; user `7ABBBA793C03C741` | Clone Dock diffuse definition/GPU. Retarget definition `+0x9C`. Inject runtime-proven resident Raven pixels. | Standalone texture rows; material group owns dependency link. |
| `TX_completionist_raven_map_emissive_63F1E18FF93B9037` | def `54584554004552558fe1f16337903bf9`; GPU `0000000000000000d216ad1542eb7da1`; user `15AD16D2A17DEB42` | Clone Dock emissive definition/GPU. Retarget definition `+0x9C`. Inject runtime-proven resident Raven pixels. | Standalone texture rows; material group owns dependency link. |
| `MAT_AE4AD85BB993F040` | `dac6009fd0f18caad2ed322463c3d0c8` | Clone `MAT_0C599DC8DC7E2170`; set `+0x10 = 1B0989158D4A2908`; preserve `+0x20 = D595197B0961F689`; retarget two art links. | Dedicated material group. |
| `MDL_completionistraven` | `e281a8d67849d97b3d5e7d88f140f59b` | Clone `MDL_mapicondock`; retarget one material link. Keep other material slots. Share `MG_mapicondock_0` ID `44b11676af9c4e0ff860108fd46b0b32`. | Dedicated model group owns material and MG link rows. |
| `goProtoMapIconCompletionistRaven` | `f29a83d61d2fe0b9bb96123ffe77225d` | Clone `goProtoNW633B8059`; replace payload-local self ID; retarget model. Keep `ANM_mapicondock`; turn three copied SCP bodies into links to stock definitions. | Dedicated prototype group. |
| `gomapiconcompletionistraven` / loader `goMapIconCompletionistRaven` | record `3d8f7153809e6db191c2d5e354f1e88c`; folded hash `584F31DC8BD6E738` | Clone map root. Set root `+0x0C` prototype record ID and `+0x1C` 56-byte loader name. | Dedicated root group. `goProtoNW633B8059` group owns one new zero-data root link. |

Map WAD delta is eight physical payloads but six typed objects: `0xA +1`, `0x10001 +1`, `0x20001 +1`, `0x2000C +1`, `0x10015 +2`. Stock records stay byte-identical.

HUD path:

| Resource | ID or hash | Donor and exact change | Physical owner |
| --- | --- | --- | --- |
| `MDL_completionistravenhud` | `4a7911dc2db72cecaf6c187a66bfd11f` | Clone `MDL_boatdock`; bind existing Raven material; share `MG_boatdock_0` ID `c3f6b4c5a8270df607ea3e6e7f891292`. | Dedicated HUD model group owns material and MG link rows. |
| `goProtoCompletionistRavenHUD` | `b2a833d6144789e8099acf85e832d652` | Clone `goProtoBoatDock`; set self ID at `+0x3A8`; retarget model. Copy local `SCP_BoatDock` body byte-identically. | Dedicated HUD prototype group. |
| local `SCP_BoatDock` | sentinel ID `baaddbbad0baaddbbaaddbbad7baaddb` | Same name, ID, flags, body as stock. New local payload instance, not new identity. | Raven HUD prototype group. |
| `gocompletionistravenhud` / loader `goCompletionistRavenHUD` | record `f0029a68d9705e95a981aab8bff0c5b8`; folded hash `45E5C7943749F81C` | Clone `goboatdock`; set `+0x0C` prototype ID and `+0x1C` loader name; preserve `+0x54` shared `goProtocompassicons` ID `502b9225361cf6449d8d85048f0b1a75`. | Dedicated root group. |

HUD adds 13 physical records and four payloads. WAD accounting adds three rows: `0x10001 +1`, `0x10005 +1`, `0x20001 +1`. HUD model payload follows proven Raven exception and is not counted by those three type rows.

Archived resident-art runtime proof also loaded newly authored `exec/patch/pc_le/completionist_v104_raven_map.texpack` (`648a16a6fabd526b56c1be8d18c5f983b5257296e28081c81edafb8790a1c6a7`) and TOC (`67cceea0d91298881f4426bf0ce5e8883da45a82905921313004df618d959053`). WAD texture definitions bind this stream data by user hash. Production adopter later pins resident `r_ui.wad`; its verifier does not pin these two pack files. No boot-options file belongs to adopted frozen verifier contract.

### `exec/dc/pc_le/wad_r_ui.dcb`

Baseline: `21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a`

Production: `765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d`

- Append map GOPool row at index 255: key `584F31DC8BD6E738`, capacity 1.
- Append HUD GOPool row at index 256: key `45E5C7943749F81C`.
- First HUD registration used capacity 1. Causal test changed only capacity to 2.
- Shift tail pointers by row bytes. Keep all old GOPool rows, memory pools, Lua tail, and non-data chunks byte-identical.

### `exec/dc/pc_le/wad_r_perm.dcb`

Pre-class base: `eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039`

Production: `85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5`

- Add type-`0x11E` `CompletionistRaven`, UID `5DC46967D3095F7E`, as packed 0x20-byte DockPoint-shaped row.
- Final class fields: `IconName = 45E5C7943749F81C`; `RadiusIconName = 0`; `InWorld_tMPIcon_Name = 21DC5A7D4AD17628`.
- Add type-`0x129` `COMPASS_INWORLD_COMPLETIONIST_RAVEN`, UID `21DC5A7D4AD17628`.
- Carrier is 0x98-byte clone of `COMPASS_INWORLD_DOCK`. Only art binding changes to `45E5C7943749F81C`. Local relocation stays self-contained from record `+0x10` to `+0x90`.
- Shift later roots and relocation endpoints while keeping old export meaning and order.

### Native routing files

| File | Baseline | Production | Raven change |
| --- | --- | --- | --- |
| `mapmaster.dcb` | `1e076f7c...` | `b930c513...` | Add `Completionist_V103_Veithurgard_Raven_01`, UID `E15E6BC82AE2773E`, realm `7CE593BC21393690`, region `A1845BEF17F0E7BB`; bind map root `goMapIconCompletionistRaven`. |
| `mapcoords.dcb` | `5d0b7591...` | `945774db...` | Add native row for Raven at `[-64.875, 12.984375, 787.5]` in `WAD_Xpl200_Funeral`. |
| `compassgraph.dcb` | `c2fa6bab...` | `d0ed78ba...` | Add edge `E15E6BC82AE2773E -> BABC033C454755A0`. |

These files give native distance and pathfinding. DCB export UIDs are export keys. WAD record IDs are local dependency identities. GOPool UIDs are folded loader-name hashes. These key spaces must not be mixed.

### Lua routing

`mapmenu.lua` moved from pre-manager control `55e6ab3771417211cab670aaa4871e5f4083dac8f00f324d5584e803bb9a11a9` to frozen production `67d069a798417b631c271f48c129fb2083591b81a31859ab94769fbbb8b01c6b`.

- Raven-origin Add and Remove query live `CompletionistRaven` manager state.
- Raven Add calls custom-class `ShowMarker`; Raven Remove calls direct `HideMarker`.
- Stock-origin action hides Raven before normal stock delegate runs.
- Async watchdog and prompt sync keep one target and correct Add/Replace/Remove text.
- No synthetic progression write exists.

## Raven vs failed Nornir

### Direct answers

- Dedicated Raven map MG? No. `MDL_completionistraven` owns link to stock `MG_mapicondock_0`.
- Why no map Dock leak? Dedicated model owns Raven material link. Dedicated material owns Raven art links. Shared MG stays byte-identical and has no Raven material binding.
- Dedicated Raven HUD MG? No. `MDL_completionistravenhud` owns link to stock `MG_boatdock_0`.
- Why no boat HUD leak? Dedicated HUD model binds Raven material. Stock `MDL_boatdock` still binds stock material. Shared MG stays byte-identical.
- Where custom Raven material bound? One zero-data dependency row in dedicated map model group and one in dedicated HUD model group.
- Which group owns local records? Material group owns texture links. Model group owns material and MG links. Prototype group owns model/animation/SCP rows. Root group owns root payload. Map parent group owns root reference. HUD prototype owns local SCP body.
- What is MG? Evidence supports data-bearing model-group resource plus model-owned dependency references. Geometry/state-container role fits graph. Exact scalar meaning is not decoded. MG is not top-level art owner in working Raven.
- Loader keys? GOPool uses folded 64-bit name hash. WAD dependencies use 16-byte record IDs. Root `+0x1C` is loader name. DCB export UID is export key. Prototype self IDs and root prototype IDs are payload-local record links. Opaque scalar meaning stays unknown.
- Wrong Candidate 2 assumption? It assumed shared stock MG was isolation bug. Raven runtime proves shared MG works when material/model/prototype/root recipe is exact. Dedicated byte-identical MG clones were extra, unproven, and did not fix first material split.

### First divergence

| Layer | Working Raven | Failed Candidate 1 | Candidate 2 |
| --- | --- | --- | --- |
| Material `+0x10` | Fresh `1B0989158D4A2908` | Fresh `E2265134DFA7BA70` | Same as failed Candidate 1 |
| Material `+0x20` | Preserve donor `D595197B0961F689` | Fresh `E2265134DFA7B641` | Same as failed Candidate 1 |
| Map MG | Share stock `MG_mapicondock_0` | Share stock | Clone to `MG_completionistnornirchest_map` |
| HUD MG | Share stock `MG_boatdock_0` | Share stock | Clone to `MG_completionistnornirchest_hud` |
| Runtime | Raven art local; no crash | Boat takeover, Raven gone, crash | Same hard failure |

Exact runtime meaning of material `+0x20` is unknown. Still, history proves it is first mechanical split and proves Raven deliberately preserved donor value. Candidate 3 follows that byte-for-byte rule. No new scalar-byte theory is used.

## Candidate 3 file manifest

Candidate output root is ignored build path `build/v0.10.4-nornir-candidate3/offline/candidate/game-root`.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `exec/wad/pc_le/r_ui.wad` | 50,080,432 | `90391a2841d3a9ad889b95d5c17fc0ee09de803a57675b6d237a98051b08c660` |
| `exec/dc/pc_le/wad_r_ui.dcb` | 4,912 | `93164584bc115b64144bef73680ce5163b7ddf48f74bfd2698fef1b165dc891a` |
| `exec/dc/pc_le/wad_r_perm.dcb` | 5,580,240 | `be453733a57a27dde5eb33e553973ec34c330e4841f7c632e4f784a8adc34350` |
| `exec/dc/pc_le/mapmaster.dcb` | 75,872 | `6285c824973e760594b7413a79645b931200e40237710600052d964602d9bff4` |
| `exec/dc/pc_le/mapcoords.dcb` | 62,640 | `b870adccf66baf0d71dd1c0774d12e5ca503415da1e9270f82d0b77c0f11cd7f` |
| `exec/dc/pc_le/compassgraph.dcb` | 282,864 | `8477f6332436959ce06b0c7e84a4871a7ff947421f9e858589e360e2e7c0d45e` |
| `mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua` | 173,348 | `ac38d76b4eea20b701ab73d3eaf9f2a23f9933b4bd4ddf5a4e9ec7197e5bc8b8` |
| `mods/lua/gameart/ui/scripts/hud/mainhud.lua` | 22,333 | `9f803bba1296c99960764aae161b2118531ba8f02dce60284207424257e01605` |
| `mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_runic.lua` | 19,644 | `67620fdab2e33186652efdd7c50c7f085e6670964e8d91556804890e382a9c3b` |
| `mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua` | 35,838 | `7b9e1b03bef0f26de9c132241f6a98750c34c6f99dbb324ea37cbcd0347c07f3` |

Structural diff against frozen Raven:

- WAD adds dedicated Nornir texture/material/model/prototype/root groups, but shares stock map/HUD MG resources. Nornir material uses fresh `+0x10` and Raven donor `+0x20`.
- GOPool adds map row 257 capacity 1 and HUD row 258 capacity 2. All first 257 rows stay exact.
- Perm DCB adds `CompletionistNornirChest` and its type-`0x129` carrier by Raven clone recipe.
- Native DCBs add one Nornir marker, one coordinate, and one graph edge. Raven rows stay present.
- Four Lua files are exact lifecycle-gate artifacts. Frozen Raven `mapmenu.lua` is exact prefix. `OPENED` remains completion authority. No synthetic progression write exists.

## Offline proof

`tools/v0.10.4/run-nornir-candidate3-offline.ps1` did this:

1. Verify frozen Raven before build.
2. Reconstruct failed Candidate 1 from frozen Raven as differential control.
3. Build Candidate 3 with one Raven-proven material field correction.
4. Reparse and serialize Candidate 3 byte-exactly.
5. Remove Candidate 3 resources and restore accounting; result equals frozen Raven WAD byte-for-byte.
6. Prove stock Dock/BoatDock and Raven named records stay byte-identical.
7. Prove no dedicated Nornir MG exists and no opaque MG payload changed.
8. Prove ten-file hash manifest, GOPool prefix, class/carrier bindings, and lifecycle artifacts.
9. Run texture reversibility, MG accounting, and WAD loader bookkeeping tests: 18 tests passed.
10. Verify frozen Raven after build.

Safety flags:

- God of War launched: false
- Installed game write: false
- Save write: false
- Progression write: false
- Marker-state write: false
- Runtime installer created or changed: false
- `runtime_install_allowed: false`

Candidate 3 needs separate installer review and later explicit runtime authorization. This task gives no runtime approval.
