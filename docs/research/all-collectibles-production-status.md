# All Collectibles Production Research Status

## Decision

Static native catalogue: **PASS**.

Runtime generation: **BLOCKED, FAIL CLOSED**.

Game test: **NOT RUN**. Exact unloaded per-object state still not proved. Unknown
state makes no marker. No game start. No game, save, or progress write.

## Scope

- Branch: `codex/all-collectibles-production-research`
- Hardening start commit: `483519b9fdc125c48a455f19c00cc79c096de4b7`
- Inputs: read-only PC WAD records, `mapmaster.dcb`, `quests.dcb`, and native Lua blobs.
- Raven code and Raven production behavior: unchanged.

## Static count

| Family | Physical rows | Raw state carriers | Tracked rows | Native target | Result |
|---|---:|---:|---:|---:|---|
| Artefacts | 45 | 45 | 11 all artefacts; 9 Ship Heads | Ship Head 10 | PASS; Ship target gap blocked |
| Lore Markers | 43 | 43 | 43 | 43 | PASS |
| Legendary Chests | 64 | 43 | 33 | 33 | PASS raw set; 31 nontracked rows stay raw |
| Nornir Chests | 22 | 29 | 0 exact | 21 | PASS raw static set; all exact joins blocked |
| Nornir Seals | 30 | child objects | parent links | n/a | PASS |
| Nornir Bells | 24 | child objects | parent links | n/a | PASS |
| Nornir Mechanisms | 12 | child objects | parent links | n/a | PASS |

Niflheim procedural rows stay out: 56 Legendary and 7 Nornir template paths.
`Lambs Cress` stays out because native row has no artefact type.

## Ship Head extraction

Result: **PASS** for physical extraction.

- State carriers: 9
- Exact transform paths: 13
- Distinct physical placements: 9
- Native tracked target: 10
- Numbered native object proof: 01 through 09

Extractor now walks every native transform parent. No record-distance, nearest
offset, nearest coordinate, or order pick remains. Shared child IDs fan out. Rows
merge only on same physical identity and same world point. Each merged row keeps
all exact carrier GUIDs and full carrier-to-placement transform paths.

| No. | WAD | Physical GUID | World XYZ | RegionSummary parent |
|---:|---|---|---|---|
| 01 | `xpl910_islandshipwreck.wad` | `fda83783-4b36-1579-d4a2-9194810c3d09` | `[-170.124322, 2.533906, -225.885511]` | `RegionSummary_ISW_Shiphead_Parent` |
| 02 | `xpl970_beachtower.wad` | `01a8ba24-409b-5fb4-9a1c-18b43669fe44` | `[-260.666945, -4.169471, 183.629049]` | `RegionSummary_BT_Shiphead_Parent` |
| 03 | `xpl980_beachwaterfall.wad` | `379728fc-47e4-a966-be1f-c9926011184b` | `[125.732797, -0.652341, 394.715973]` | `RegionSummary_BW_Shiphead_Parent` |
| 04 | `xpl950_beachmaze.wad` | `5bb11ed5-419b-42ca-ba81-3598d29ca473` | `[-182.692799, -0.495932, 312.858455]` | `RegionSummary_BM_Shiphead_Parent` |
| 05 | `cal100_hub.wad` | `4a3d3149-42f1-87f6-9ee5-b78302e118fe` | `[189.612320, 6.012498, 55.892853]` | `RegionSummary_CALS_Shiphead_Parent` |
| 06 | `xpl940_beachcave.wad` | `7d8a35dc-4d6a-abf8-065e-1ead0c470fcc` | `[100.532954, 2.020625, -176.915965]` | `RegionSummary_BC_Shiphead_Parent` |
| 07 | `xpl980_beachwaterfall.wad` | `6cffc988-4efa-77b4-24ba-f987adfdba6a` | `[115.259514, 5.969724, 223.703513]` | `RegionSummary_BW_Shiphead_Parent` |
| 08 | `cal100_hub.wad` | `f7fbfc3f-4499-1b3d-a378-71879e6de737` | `[22.059830, -4.013092, 110.690048]` | `RegionSummary_CALS_Shiphead_Parent` |
| 09 | `xpl960_beachship.wad` | `bd9a46a3-4b8f-d466-0be2-129e27fa4004` | `[-223.796620, 5.981133, -115.035329]` | `RegionSummary_CALS_Shiphead_Parent` |

Full catalogue IDs, state carrier GUIDs, record IDs, native object evidence, and
exact transform paths live in `all-collectibles.json`.

## Ship Head target 10 vs physical 9

Result: **BLOCKED_EXACT_REASON_UNKNOWN**.

Native data proves 9 carriers, 13 branch paths, and 9 objects. It does not prove
a tenth carrier, cut object, legacy object, or quest duplicate. Keep 9 physical
markers. Treat target 10 as native bookkeeping gap until exact proof exists.

## Nornir join

- Physical: 22
- Native tracked target: 21
- Exact native reference-chain joins: 0
- `PASS_EXACT`: 0
- `BLOCKED_EXACT_REASON_UNKNOWN`: 22
- Region/count inference: none

The former 20-row WAD-to-quest table was not independent proof. All 20 source
WADs contain zero copies of their claimed `RegionSummary_RunicChest` target.
The extractor now accepts a join only when a machine-readable evidence row is
`PASS_EXACT`, names native source files, and contains an exact binding-edge
record. WAD names, filename prefixes, human region labels, map discovery,
candidate membership, coordinates, ordering, and target counts cannot join.

Each audit row keeps five concepts separate: physical object, exact source
level/WAD identity, map/region ownership, RegionSummary target, and loaded versus
unloaded completion-state oracle. Source placement and target records exist for
the old claims, but the level/object-to-target edge does not. Thus all stay
blocked.

| WAD | Physical GUID | Proposed RegionSummary target | Native proof checked | Status |
|---|---|---|---|---|
| `alf210_lakedarklh.wad` | `e00c75d2-4c76-b498-de4c-1f85c997c65e` | `RegionSummary_RunicChest_Parent_Alfheim` | placement + `wad_alf210_lakedarklh.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `alf320_trenchadark.wad` | `3ec0daa8-4892-2cad-4fb3-0c8bb93c171f` | `RegionSummary_RunicChest_Parent_Alfheim` | placement + `wad_alf320_trenchadark.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `alf340_trenchbdark.wad` | `9a92c243-4083-2c21-07ff-7d997c9fcbda` | `RegionSummary_RunicChest_Parent_Alfheim` | placement + `wad_alf340_trenchbdark.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `alf690_lakelightlh.wad` | `522448bf-4d91-b0f1-9de6-adbd1c77d709` | `RegionSummary_RunicChest_Parent_Alfheim` | placement + `wad_alf690_lakelightlh.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `cal500_runevault.wad` | `f8548c57-4dc6-7cba-277c-5cb31099648b` | `RegionSummary_RunicChest_Parent_TyrsVault` | placement + `wad_cal500_runevault.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `foot100_base.wad` | `a6ac8eeb-4ea2-545a-b05d-f19e8ea6ee8f` | `RegionSummary_RunicChest_Parent_Foothills` | placement + `wad_foot100_base.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `for600_spire.wad` | `6d18634c-4e86-282d-1cfa-0e84f6d5654f` | `RegionSummary_RunicChest_Parent_Forest` | placement + `wad_for600_spire.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `helr100_docks.wad` | `6fc8ac79-4c63-bf63-a137-36b7cd3c7f25` | none; native untracked reward | placement + callback ownership + no Helheim RunicChest target | **BLOCKED_EXACT_REASON_UNKNOWN** binding; **PASS_EXPLAINED** untracked class |
| `peak140_caverndark.wad` | `f8ac74b9-414e-59e7-64d8-738182c00663` | `RegionSummary_RunicChest_Parent_Peakspass` | placement + `wad_peak140_caverndark.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `peak720_summitascenthub.wad` | `c0cf4119-40ba-d7d0-0042-afa7a46f5514` | `RegionSummary_RunicChest_Parent_Peakspass` | placement + `wad_peak720_summitascenthub.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `riv225_dangerscave.wad` | `45bbcd15-458c-d30c-3338-a7b3dab9b3d9` | `RegionSummary_RunicChest_Parent_Riverpass` | placement + `wad_riv225_dangerscave.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `riv325_dangersexit.wad` | `7d8b4043-40e8-ef8e-db40-96b3a1a1e3fc` | `RegionSummary_RunicChest_Parent_Riverpass` | placement + `wad_riv325_dangersexit.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `riv420_forestboarstart.wad` | `d2cacb84-426f-d68d-504a-11ae125c2b62` | `RegionSummary_RunicChest_Parent_Riverpass` | placement + `wad_riv420_forestboarstart.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `riv475_freyahouseext.wad` | `69780ade-492b-0891-1948-4199e5423527` | `RegionSummary_RunicChest_Parent_Riverpass` | placement + `wad_riv475_freyahouseext.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `riv925_freyacave.wad` | `0f0cc7ca-4842-3bb2-96f6-ddbed87a8f3b` | `RegionSummary_RunicChest_Parent_Riverpass` | placement + `wad_riv925_freyacave.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `xpl100_httk.wad` | `d8e4c774-44fe-09d0-a960-198ab802058e` | `RegionSummary_RunicChest_Parent_HTTK` | placement + `wad_xpl100_httk.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `xpl200_funeral.wad` | `c190d593-4070-6bb7-9925-cb9f2d5867cf` | `RegionSummary_RunicChest_Parent_VikingFuneral` | placement + `wad_xpl200_funeral.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `xpl850_dungeonforest.wad` | `3f3a8e78-44ff-44f5-7da0-24b2efce93dc` | `RegionSummary_RunicChest_Parent_ForestDungeon` | placement + `wad_xpl850_dungeonforest.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `xpl920_islandclimb.wad` | `a336e184-4ac7-c90b-6cd6-288e2cdab274` | `RegionSummary_RunicChest_Parent_IslandClimb` | placement + `wad_xpl920_islandclimb.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `xpl940_beachcave.wad` | `a2cdfc7a-4f0a-b68e-ac21-2bb108cd35b7` | `RegionSummary_RunicChest_Parent_BeachCave` | placement + `wad_xpl940_beachcave.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `xpl950_beachmaze.wad` | `c02f0190-49d5-0ea0-146c-478fd46f4a49` | `RegionSummary_RunicChest_Parent_BeachMaze` | placement + `wad_xpl950_beachmaze.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |
| `xpl970_beachtower.wad` | `6b701107-4e78-df82-ecd5-08b6b1a8444f` | `RegionSummary_RunicChest_Parent_BeachTower` | placement + `wad_xpl970_beachtower.dcb` WAD identity; no binding edge | **BLOCKED_EXACT_REASON_UNKNOWN** |

`cal500_runevault.wad` placement
`f8548c57-4dc6-7cba-277c-5cb31099648b` stays unjoined.

Result: **BLOCKED_EXACT_REASON_UNKNOWN**.

Exact placement has `RuneChestOpened` callback into `cal500_runevault` level
script. Level script names `chest_locked_tier4_cal500_1`, `bRuneChestOpened`, and
`TyrsVault`. But target name only appears in shared `interact_chest_standard`
blob. No exact callback-to-RegionSummary update, GUID chain, or quest reference
binds this object to `RegionSummary_RunicChest_Parent_TyrsVault`.

Helheim placement `6fc8ac79-4c63-bf63-a137-36b7cd3c7f25`:
**PASS_EXPLAINED**. Placement and `helr100_docks` level script share
`HelR100_TripleChest_Callback`. Native quest data has no Helheim RunicChest
target. Class: `level_scripted_untracked_triple_chest_reward`.

## Legendary user class

Raw 64 physical rows stay. 33 map-summary rows stay tracked. Remaining 31 stay
unresolved nontracked raw research. No new production eligibility guess made.
Production marker eligibility stays separate from raw physical membership.

## Runtime gate

Loaded state proof still holds. Exact unloaded/pre-install lookup by catalogue
instance key does not. Nornir child limits still hold. Runtime generation stays
off. Unknown state stays hidden.

## Output

- `config/collectibles/v0.10.5/all-collectibles.json`
- `docs/research/all-collectibles-native-audit.json`
- `tools/v0.10.5/collectible_catalogue.py`
- `tools/v0.10.5/test_collectible_catalogue.py`
- `NEXT_STEPS.md`

## Verification

- 84 tests passed; 0 failed; 0 skipped.
- Four Raven Lua 5.1 tests ran with local CPython 3.14 and existing
  `dist/re-tools/lupa`; none skipped.
- Two full native generations were byte-identical.
- Catalogue SHA-256:
  `e2d7cdc7c9923c586bdcdcae69d4a23e7f7a5f5d5e825ff540bdefe589713bec`.
- Audit SHA-256:
  `18b7bd4a3549ef115cc7dc1731e40abee889cc82631219e7a4e23ae1d8e1cf9b`.
