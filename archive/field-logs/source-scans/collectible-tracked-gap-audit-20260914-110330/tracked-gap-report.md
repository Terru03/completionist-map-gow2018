# Collectible tracked-gap audit

Status: **TRACKED_GAPS_AUDITED_NO_AUTO_JOIN**

This report is evidence-only. Same-region rows are candidates, not exact native joins, and the catalogue is not modified.

## Nornir Chest

- Physical rows: 22
- Exact joined rows: 20
- Native tracked target total: 21

### Native targets

- `RegionSummary_RunicChest_Parent_Alfheim` (Alfheim / Alfheim): target=4 exact_rows=4 deficit=0
- `RegionSummary_RunicChest_Parent_BeachCave` (Midgard / BeachCave): target=1 exact_rows=1 deficit=0
- `RegionSummary_RunicChest_Parent_BeachMaze` (Midgard / BeachMaze): target=1 exact_rows=1 deficit=0
- `RegionSummary_RunicChest_Parent_BeachTower` (Midgard / BeachTower): target=1 exact_rows=1 deficit=0
- `RegionSummary_RunicChest_Parent_Foothills` (Midgard / Foothills): target=1 exact_rows=1 deficit=0
- `RegionSummary_RunicChest_Parent_Forest` (Midgard / Forest): target=1 exact_rows=1 deficit=0
- `RegionSummary_RunicChest_Parent_ForestDungeon` (Midgard / ForestDungeon): target=1 exact_rows=1 deficit=0
- `RegionSummary_RunicChest_Parent_HTTK` (Midgard / HTTK): target=1 exact_rows=1 deficit=0
- `RegionSummary_RunicChest_Parent_IslandClimb` (Midgard / IslandClimb): target=1 exact_rows=1 deficit=0
- `RegionSummary_RunicChest_Parent_Peakspass` (Midgard / Peakspass): target=2 exact_rows=2 deficit=0
- `RegionSummary_RunicChest_Parent_Riverpass` (Midgard / Riverpass): target=5 exact_rows=5 deficit=0
- `RegionSummary_RunicChest_Parent_TyrsVault` (Midgard / TyrsVault): target=1 exact_rows=0 deficit=1
- `RegionSummary_RunicChest_Parent_VikingFuneral` (Midgard / VikingFuneral): target=1 exact_rows=1 deficit=0

### Unmatched physical rows

- `nornir_chest_6fc8ac794c63bf63a13736b7cd3c7f25` — helr100_docks.wad — Helheim / Helheim (native_level_namespace); same-region target candidates: none; explicit RegionSummary attributes: none; world=[2228.758056640625, -338.0022277832031, 682.715087890625]
- `nornir_chest_f8548c574dc67cba277c5cb31099648b` — cal500_runevault.wad — Midgard / CalderaTemple (native_level_namespace); same-region target candidates: none; explicit RegionSummary attributes: none; world=[-93.23381805419922, -5.2519025802612305, 1.27968430519104]

## Ship Head

- Physical rows: 7
- Exact joined rows: 7
- Native tracked target total: 10

### Native targets

- `RegionSummary_BC_Shiphead_Parent` (Midgard / BeachCave): target=1 exact_rows=1 deficit=0
- `RegionSummary_BM_Shiphead_Parent` (Midgard / BeachMaze): target=1 exact_rows=1 deficit=0
- `RegionSummary_BSW_Shiphead_Parent` (Midgard / BeachShipwreck): target=1 exact_rows=0 deficit=1
- `RegionSummary_BT_Shiphead_Parent` (Midgard / BeachTower): target=1 exact_rows=1 deficit=0
- `RegionSummary_BW_Shiphead_Parent` (Midgard / BeachWaterfall): target=1 exact_rows=1 deficit=0
- `RegionSummary_CALS_Shiphead_Parent` (Midgard / CalderaShores): target=4 exact_rows=2 deficit=2
- `RegionSummary_ISW_Shiphead_Parent` (Midgard / IslandShipwreck): target=1 exact_rows=1 deficit=0

### Unmatched physical rows

- none

## Interpretation

A row may only be promoted to a tracked quest join when native object/quest evidence proves that exact relationship. Region equality or a count deficit alone is insufficient.

Runtime generation remains disabled and no save/progression state was accessed or written.
