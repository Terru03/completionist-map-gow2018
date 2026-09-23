# Legendary Chest RegionSummary link audit

Static result: **0/33 unique chest-to-RegionSummary links proved**; 33/33 unresolved. No runtime work may start from this result.

## Native route found

The extracted game Lua `interact_chest_standard.lua`, lines 435-443,
calls `game.Map.FindPlayerRegion()` when a Legendary Chest opens.
It updates the resulting region aggregate. Two region-name branches
call the Tyr quest targets. The call takes no physical chest GUID.
The active player region at each chest point has no proved static
chest-to-zone edge. This breaks the assumed per-chest map link model.

The pinned `mapmaster.dcb` holds the proposed target names; `quests.dcb`
holds target records. These are shared summary data. A target name,
WAD name, target count, or near point cannot prove chest ownership.
The 18 proposed quest targets sum to 33 chests, but this count cannot bind a row.
Exact physical GUID and placement-record patterns had 0 hits across 561 native DCB files.
The pinned mapmaster has 382 authored markers and no
Legendary/Chest-named icon class. No per-chest map point was found.
This negative scan does not rule out a dynamic or differently named path.

| WAD | Physical GUID | Proposed target | Target basis | Link |
| --- | --- | --- | --- | --- |
| `alf600_templeint.wad` | `040af4fa-440e-f7ba-52f8-e8b317ac3200` | `RegionSummary_LegendaryChest_Parent_Alfheim` | `unique_region_family_inference` | unresolved |
| `foot400_arena.wad` | `0a04b4de-469f-3b03-0064-d6827966b213` | `RegionSummary_LegendaryChest_Parent_Foothills` | `unique_region_family_inference` | unresolved |
| `riv475_freyahouseext.wad` | `11e085df-4bd4-7dee-e3a3-448bff9efc62` | `RegionSummary_LegendaryChest_Parent_Riverpass` | `unique_region_family_inference` | unresolved |
| `xpl900_islandarch.wad` | `23d3213f-45e3-8b63-2ed8-048e876e472d` | `RegionSummary_LegendaryChest_Parent_IslandArch` | `unique_region_family_inference` | unresolved |
| `riv925_freyacave.wad` | `36cb588e-41cb-27a4-6680-52b4529b98a6` | `RegionSummary_LegendaryChest_Parent_Riverpass` | `unique_region_family_inference` | unresolved |
| `alfdgn110_main.wad` | `48f9e169-4dc7-22a5-49f4-2893d5b79d9f` | `RegionSummary_LegendaryChest_Parent_Alfheim` | `unique_region_family_inference` | unresolved |
| `xpl980_beachwaterfall.wad` | `50480b3a-40fe-25c4-770f-81a7261cbcb8` | `RegionSummary_LegendaryChest_Parent_BeachWaterfall` | `unique_region_family_inference` | unresolved |
| `foot200_mid.wad` | `510bd864-41ac-6a7b-71d4-f59321c2a08f` | `RegionSummary_LegendaryChest_Parent_Foothills` | `unique_region_family_inference` | unresolved |
| `xpl920_islandclimb.wad` | `52934398-4fc3-1350-4ac2-0da874d05c01` | `RegionSummary_LegendaryChest_Parent_IslandClimb` | `unique_region_family_inference` | unresolved |
| `hel100_calderaheldressing.wad` | `5618d560-4269-40a0-2e5b-39a340c0c209` | `RegionSummary_LegendaryChest_Parent_Helheim` | `unique_region_family_inference` | unresolved |
| `cal100_hub.wad` | `5b424870-484e-691c-e32d-19be71a03059` | `RegionSummary_LegendaryChest_Parent_CalderaShores` | `unique_region_family_inference` | unresolved |
| `xpl850_dungeonforest.wad` | `7a71d104-452e-16e3-9a25-bb8a14e47343` | `RegionSummary_LegendaryChest_Parent_ForestDungeon` | `unique_region_family_inference` | unresolved |
| `hel100_calderaheldressing.wad` | `8002f429-4486-1752-3d18-9cbd93b23d4b` | `RegionSummary_LegendaryChest_Parent_Helheim` | `unique_region_family_inference` | unresolved |
| `xpl100_httk.wad` | `890a24d2-4d28-64a1-567a-f691c615870f` | `RegionSummary_LegendaryChest_Parent_HTTK` | `unique_region_family_inference` | unresolved |
| `riv100_dangersentrance.wad` | `8aabd22a-44df-8f25-a955-fe8e04fc0d95` | `RegionSummary_LegendaryChest_Parent_Riverpass` | `unique_region_family_inference` | unresolved |
| `alf370_moatscripting.wad` | `91a9f92a-45d2-d3fd-b922-79b4612ab5d7` | `RegionSummary_LegendaryChest_Parent_Alfheim` | `unique_region_family_inference` | unresolved |
| `xpl900_islandarch.wad` | `9226bd44-4f0f-0b95-dbeb-7c927c6b317b` | `RegionSummary_LegendaryChest_Parent_IslandArch` | `unique_region_family_inference` | unresolved |
| `hel300_mainbridge.wad` | `957a57b3-456b-d17f-d247-51a66dbcf01c` | `RegionSummary_LegendaryChest_Parent_Helheim` | `unique_region_family_inference` | unresolved |
| `xpl910_islandshipwreck.wad` | `9c0dc602-456a-00fa-44bc-a1a3b599cf67` | `RegionSummary_LegendaryChest_Parent_IslandShipwreck` | `unique_region_family_inference` | unresolved |
| `xpl400_huldramines.wad` | `9d7648ab-43bf-99f9-0b0c-bd86b0a998f1` | `RegionSummary_LegendaryChest_Parent_HuldraMine01` | `unique_region_family_inference` | unresolved |
| `peak200_chimneylow.wad` | `9f29650a-4a8a-5d0e-b8bc-43af1dbd3d68` | `RegionSummary_LegendaryChest_Parent_Peakspass` | `unique_region_family_inference` | unresolved |
| `xpl980_beachwaterfall.wad` | `ace99ef5-472a-bcba-c29b-d2b396a3fdf3` | `RegionSummary_LegendaryChest_Parent_BeachWaterfall` | `unique_region_family_inference` | unresolved |
| `riv925_freyacave.wad` | `ae9454d5-4e9c-9a23-f219-41b41a4038d3` | `RegionSummary_LegendaryChest_Parent_Riverpass` | `unique_region_family_inference` | unresolved |
| `alfdgn210_main.wad` | `b97f559c-471f-ab88-50a2-ae8741370020` | `RegionSummary_LegendaryChest_Parent_Alfheim` | `unique_region_family_inference` | unresolved |
| `xpl960_beachship.wad` | `b9e3be9a-46c2-48cc-0ddc-159643259c52` | `RegionSummary_LegendaryChest_Parent_BeachShipwreck` | `unique_region_family_inference` | unresolved |
| `alf340_trenchbdark.wad` | `c14a0f2b-4559-d859-3478-54bccb307f63` | `RegionSummary_LegendaryChest_Parent_Alfheim` | `unique_region_family_inference` | unresolved |
| `cal500_runevault.wad` | `d0b93e27-4754-785e-0823-5285bd6b78f2` | `RegionSummary_LegendaryChest_Parent_TyrsVault` | `corrected_map_count_scope_proof` | unresolved |
| `peak720_summitascenthub.wad` | `d63295f2-44f3-3021-9b00-3c913c0dab69` | `RegionSummary_LegendaryChest_Parent_Peakspass` | `unique_region_family_inference` | unresolved |
| `xpl250_funeralinterior.wad` | `d6d6acfe-444f-2ad1-0b49-cea2ba85a1eb` | `RegionSummary_LegendaryChest_Parent_VikingFuneral` | `unique_region_family_inference` | unresolved |
| `xpl910_islandshipwreck.wad` | `d6fb0fd6-4364-453c-c3e3-34a2454e0b75` | `RegionSummary_LegendaryChest_Parent_IslandShipwreck` | `unique_region_family_inference` | unresolved |
| `xpl950_beachmaze.wad` | `ede160a5-4530-f55a-7667-f5a39257843c` | `RegionSummary_LegendaryChest_Parent_BeachMaze` | `unique_region_family_inference` | unresolved |
| `cal740_leftwing.wad` | `f714d2d8-45a3-dd9e-2880-8db4655e757f` | `RegionSummary_LegendaryChest_Parent_TheHallofTyr` | `corrected_map_count_scope_proof` | unresolved |
| `peak500_chimneytop.wad` | `ff46dfab-43ef-cfc6-f0f3-82a33e2b571d` | `RegionSummary_LegendaryChest_Parent_Peakspass` | `unique_region_family_inference` | unresolved |

## Stop point

All 33 placement chains stay valid. This audit changes no catalogue row.
Map-side world point and point comparison stay null for all 33.
Next proof needs an exact source that binds each chest interaction
point to the player region selected by `FindPlayerRegion()`, or another
native chest-to-summary edge. No region assignment is guessed here.
Chest #34 stays out of scope. Game stayed closed. No mapmaster,
progression, persistence, runtime marker, or Raven file changed.

Exact IDs, hashes, record offsets, and reasons are in
`legendary-region-link-audit.json`; flat rows are in
`legendary-region-link-table.csv`.
