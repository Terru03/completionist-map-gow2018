# Research notes

## Map pipeline findings

The decompiled map UI indicates that the native map obtains marker records through:

```lua
Map.GetMarkersInfoTable(regionId)
```

The stock UI recognises marker/token states including:

- `tweaks.eTokenState.kDiscovered`
- `tweaks.eTokenState.kDiscoveredButLocked`
- `tweaks.eTokenState.kUndiscovered`

The stock map's rendering path creates icons with:

```lua
Map.CreateMarkerIcon(markerId, regionId, "")
```

The stock waypoint flow ultimately uses:

```lua
game.Compass.ShowMarker(markerID, markerType)
```

but only for marker IDs carrying supported compass-marker flags.

## v0.1 lesson

Do not assume an undiscovered marker record is accepted by the same icon construction path as a discovered marker. The crash strongly suggests the hidden state is intentionally filtered before icon creation, or that additional discovery-time state/data is required.

## v0.2 result

For Alfheim, `Map.GetMarkersInfoTable(regionId)` returned 27 records, including 23 `kUndiscovered`. This proved hidden marker records are visible to Lua.

## v0.3.1 Midgard result

Midgard exposed:

- 318 marker records
- 312 unique marker IDs
- 74 `kDiscovered`
- 244 `kUndiscovered`

The 244 hidden records are mostly infrastructure rather than collectibles. Major groups include quest objectives, docks, fights, fast travel, area entrances and info-only markers. Therefore `kUndiscovered` cannot be used as a direct completionist filter.

## v0.4 result: native marker-table path rejected for collectibles

Midgard's realm summary is currently:

- total progress: `148 / 225`
- SideQuests: `8 / 12`
- Artifacts: `26 / 34`
- FastTravelLocation: `23 / 30`
- VendorLocation: `11 / 13`
- LoreMarker: `32 / 37`
- Ravens: `19 / 43`
- Valkyrie: `0 / 4`
- ValkyrieQueen: `0 / 1`
- RunicChest: `9 / 17`
- LegendaryChest: `15 / 25`
- PocketRift: `5 / 9`

Every one of the 244 hidden marker records returned `candidateFlags=<none>` for the tested collectible strings.

The strongest evidence is region-level mismatch. For example:

- Foothills reports Ravens `0 / 2`, yet its hidden map records are ordinary quest/fast-travel records.
- Forest reports Artifacts `2 / 4`, Ravens `0 / 1`, PocketRift `0 / 1`, RunicChest `0 / 1`, but its hidden records are quest/fight/travel records.
- The central Lake of Nine region reports LoreMarker `5 / 7`, PocketRift `3 / 4`, LegendaryChest `0 / 1`, again with no collectible-typed hidden map records.
- Peakspass reports missing artefacts, ravens, legendary chests and runic chests, but none of its hidden native map markers carry those collectible categories.

Conclusion: collectible completion data and collectible world objects are tracked separately from the native POI marker table.

## Gameplay-object path

A public decompiled-script mirror (`MorseTheCode/GoWLUA`) confirms that the actual collectible scripts retain live object references, exact completion state and region-summary linkage.

### Odin's Ravens

`gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua` contains:

- `thisObj`
- `ravenKilled`
- `regionSummaryQuest`
- `thisObj:GetWorldPosition()`
- checkpoint save/restore for `ravenKilled`

### Artefacts

`interact_loot_artifact.lua` contains:

- `thisObj`
- acquisition `state` (`ENABLED`, `DISABLED`, `ACQUIRED`)
- `regionSummaryQuest`
- artefact subtype / unique resource
- checkpoint save/restore

### Lore markers / rune reads

`langcheckruneread.lua` contains:

- `thisObj`
- `regionSummaryQuest`
- `mapSummaryComplete`
- journal resource identifiers
- checkpoint save/restore for `mapSummaryComplete`

### Pocket rifts

`interact_loot_pocketrift.lua` contains:

- `thisObj`
- `hasOpened`
- `regionSummaryQuest`
- WAD name
- checkpoint save/restore for `hasOpened`

### Legendary / Runic chests

`interact_chest_standard.lua` contains:

- `thisObj`
- `state` including `OPENED`
- `ChestType`
- `WADName`
- code that increments region-summary categories `LegendaryChest` and `RunicChest`

## v0.5 / v0.5.1 result: local WAD streaming confirmed

The first v0.5.1 test loaded a Midgard save outside the target Raven area. The override existed and compiled, but the loader never loaded `precisionchallenge.lua` and no Raven instrumentation ran.

A targeted test then entered Veithurgard. The loader loaded `precisionchallenge.lua`, and `WAD_Xpl200_Funeral` instantiated exactly three Raven gameplay objects:

```text
1. precision_challenge_raven_perch
   regionQuest=RegionSummary_VF_Raven_Parent
   killed=false
   x=-64.850898742676
   y=12.987384796143
   z=787.30694580078

2. precision_challenge_raven_perch
   regionQuest=RegionSummary_VF_Raven_Parent
   killed=true
   x=-127.96075439453
   y=15.577629089355
   z=690.07580566406

3. precisionchallenge_ravenhover
   regionQuest=RegionSummary_VF_Raven_Parent
   killed=true
   x=122.60485076904
   y=17.374271392822
   z=679.21160888672
```

The region summary independently reported Ravens `2 / 3`. Therefore the object-level restored state matches the completion summary exactly: two completed and one remaining.

### What this proves

1. Collectible gameplay objects expose exact world coordinates.
2. Their restored per-object completion state can distinguish completed from remaining collectibles.
3. `regionSummaryQuest` gives a stable link to the map-summary region/category accounting.
4. Collectible objects are not instantiated realm-wide. Their scripts appear when the corresponding WAD is streamed.
5. Runtime enumeration alone cannot reveal every remaining collectible immediately after opening the map.

## Architecture consequence

The practical architecture is now hybrid:

```text
static/generated catalogue from game assets
    -> collectible identity + WAD + region + world position

live save/progression/object state
    -> completed vs remaining

remaining catalogue entries
    -> map representation
    -> waypoint/compass target
```

Runtime instrumentation is still valuable as a validator for the catalogue and for learning each collectible type's completion-state semantics, but the final mod should not require the user to visit every WAD before markers become available.

## v0.6 research target

Use the known remaining Veithurgard Raven as a deterministic first map/compass test target:

```text
WAD_Xpl200_Funeral
RegionSummary_VF_Raven_Parent
(-64.850898742676, 12.987384796143, 787.30694580078)
```

Questions to answer:

1. How does the map convert an arbitrary world position into map-space?
2. Can Lua construct a synthetic native marker record accepted by `Map.CreateMarkerIcon()` and `game.Compass.ShowMarker()`?
3. If no native creation API exists, can we create a UI-only map icon at the converted map position and drive a separate compass target toward the world coordinate?
4. How should collectible catalogue entries be keyed so they can be reconciled against save/progression state without depending on unstable runtime object IDs?

## Safety rule

Do not:

- pass arbitrary `kUndiscovered` stock records to `Map.CreateMarkerIcon()`
- call `Map.ChangeMarkerState()` on unrelated stock markers
- increment region-summary quests
- mutate collectible completion state
- write synthetic save data
