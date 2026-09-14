# All Collectibles Production Research Status

## Decision

Static native catalogue: **PASS**.

Runtime generation: **BLOCKED, FAIL CLOSED**.

Game test: **NOT RUN**. Exact unloaded per-object state still not proved. Unknown
state makes no marker. No game start. No game, save, or progress write.

## Scope

- Branch: `codex/all-collectibles-production-research`
- Legendary-classification hardening start commit: `0f8774b06759763defc31fb710264f7966cf610c`
- Inputs: read-only PC WAD records, `mapmaster.dcb`, `quests.dcb`, and native Lua blobs.
- Raven code and Raven production behavior: unchanged.

## Static count

| Family | Physical rows | Raw state carriers | Tracked rows | Native target | Result |
|---|---:|---:|---:|---:|---|
| Artefacts | 45 | 45 | 11 all artefacts; 9 Ship Heads | Ship Head 10 | PASS; Ship target gap blocked |
| Lore Markers | 43 | 43 | 43 | 43 | PASS |
| Legendary Chests | 64 | 43 | 33 | 33 | PASS raw set; 27 trial rewards excluded; 4 unresolved |
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

Raw catalogue membership and production eligibility are now separate. All 64
physical rows stay. All 33 existing exact RegionSummary rows stay
`tracked_legendary` / `tracked_collectible`; none were downgraded.

Of 31 nontracked physical rows, 27 are `PASS_EXACT` `trial_reward` and therefore
`exclude_trial_reward`. Positive native proof is the exact placement identity
(`goarenaNN_{bronze|silver|gold}_legendary_tierN...` or
`gosurtrs_trial_{bronze|silver|gold}_{l|r}`) plus an exact transform-chain owner
record (`go{bronze|silver|gold}reward` or `goarenaNN_chestelevator_{l|r}`). Each
audit row records WAD SHA-256, physical and state GUIDs, record IDs, offsets,
world XYZ, attributes, and the full chain. WAD filename, region, absence from
RegionSummary, coordinates, ordering, nearest object, and target counts do not
classify these rows.

Production-excluded catalogue IDs:

- `legendary_chest_0656339a4c04a3698b80c0ae57ed2e24`
- `legendary_chest_0e87c24a40632a8e064968874d2b33fc`
- `legendary_chest_0f68bc8d434fc653dd119d88fe25ac39`
- `legendary_chest_1426a75646869538a1aab6834be04997`
- `legendary_chest_167c0b9e442495b37cbbe6b0a59421c9`
- `legendary_chest_1ea4b3d24aaae3001a7c779588579d23`
- `legendary_chest_2106ba90475100c6a58ea0ac3e44f84b`
- `legendary_chest_3398a59742fb97a1ffa90a999575ad86`
- `legendary_chest_3a43afc448ef450e8db6478342603b96`
- `legendary_chest_4e9ceb3946ffc7ee27f94a8421e26426`
- `legendary_chest_5ee9b99949168a003242f99b3a7a9e40`
- `legendary_chest_62733a594d3d75eafab57d8f356c5e5d`
- `legendary_chest_778c66804cd49dc1154a6e87d91b6f94`
- `legendary_chest_7e85dc2d4905c3d53d06388e05fa3a3d`
- `legendary_chest_8666ad60456472e7c4678183988ff6a6`
- `legendary_chest_86a82b8b451b29c7671ece9c0c3b02b6`
- `legendary_chest_8751f6cc4bc76143fafe0fbbd24835e7`
- `legendary_chest_986af1ac43ce92971070738ef0f0e26f`
- `legendary_chest_9af2b5194b2e647634c4a89eebf594cd`
- `legendary_chest_a727239b4ba27f22bd1f34bef81b9c26`
- `legendary_chest_a7fa046d4390121fef12309f326e5a73`
- `legendary_chest_a9e88e5d4159d86d6bbdaf98ea1421ef`
- `legendary_chest_af802a024b7ebfbf480f449f9c033616`
- `legendary_chest_b7e0c5d14e1cf09b614010bbc6cacf16`
- `legendary_chest_d389c19140167b88d7a6819e7c392c93`
- `legendary_chest_d3cc74624839fc657d7ecd8f255e0113`
- `legendary_chest_ed7fec9d410885a9729dc3baab012f1f`

Four rows remain `unresolved_nontracked` / `unresolved` with
`BLOCKED_EXACT_REASON_UNKNOWN`. They must not become normal completionist
markers:

- `legendary_chest_0e27df5f4bc5f2545a43178d0115312b` (`stn200_lakeext.wad`)
- `legendary_chest_a24ac28d4ea8598d880d7bb099b8b8be` (`xpl300_stronghold.wad`)
- `legendary_chest_d0b93e274754785e08235285bd6b78f2` (`cal500_runevault.wad`)
- `legendary_chest_f714d2d845a3dd9e28808db4655e757f` (`cal740_leftwing.wad`)

The audit has one structured classification record for every one of the 64 raw
rows. Exact class counts: tracked 33, trial reward 27, unresolved 4. No story,
quest, scripted, or other-native class is claimed.

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

- Full v0.10.5 discovery: 90 tests passed, 0 failed; 4 Lua tests skipped under
  CPython 3.13 because that interpreter lacks the Lua runtime.
- The same four Raven Lua 5.1 tests then ran with local CPython 3.14 and existing
  `dist/re-tools/lupa`: 4 passed, 0 failed, 0 skipped.
- Two full native generations were byte-identical.
- Catalogue SHA-256:
  `df4a44914426599a52ab28bf165142941f950f407b9919b6519ee65968b51ae7`.
- Audit SHA-256:
  `f7e388bb96f75085cd63abc4b154d0a80f474111355a00d0ad13f6c0baf18bc0`.
