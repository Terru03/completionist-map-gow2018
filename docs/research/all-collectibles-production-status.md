# All Collectibles Production Research Status

## Decision

Static native catalogue: **PASS**.

Runtime generation: **BLOCKED, FAIL CLOSED**.

Game test: **NOT RUN**. Exact unloaded per-object state still not proved. Unknown
state makes no marker. No game start. No game, save, or progress write.

## Scope

- Branch: `codex/all-collectibles-production-research`
- Start commit: `d0600d90193c1327119d428983bc0a29fa97af1a`
- Inputs: read-only PC WAD records, `mapmaster.dcb`, `quests.dcb`, and native Lua blobs.
- Raven code and Raven production behavior: unchanged.

## Static count

| Family | Physical rows | Raw state carriers | Tracked rows | Native target | Result |
|---|---:|---:|---:|---:|---|
| Artefacts | 45 | 45 | 11 all artefacts; 9 Ship Heads | Ship Head 10 | PASS; Ship target gap blocked |
| Lore Markers | 43 | 43 | 43 | 43 | PASS |
| Legendary Chests | 64 | 43 | 33 | 33 | PASS raw set; 31 nontracked rows stay raw |
| Nornir Chests | 22 | 29 | 20 | 21 | PASS static; one tracked join blocked |
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
- Exact native level/zone ownership joins: 20
- Region/count inference: none

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
