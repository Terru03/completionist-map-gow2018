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

This is ideal for a runtime registry if enough raven objects instantiate globally.

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

## v0.5 strategy

Patch only `precisionchallenge.lua` from the user's own `mods/lua_source` copy and log each raven in `OnStart`, after checkpoint restoration should have populated `ravenKilled` and before the script early-returns for already-killed birds.

Log:

- level/WAD name
- object name and runtime ID
- `regionSummaryQuest`
- `ravenKilled`
- world X/Y/Z

This answers the object-lifetime question without mutating gameplay.

If all or most of Midgard's 43 raven objects appear on loading a save, build a global runtime collectible registry. If only a local subset appears, runtime enumeration is insufficient for whole-realm reveal and we should extract positions from unloaded game assets/WADs into a generated cache.

## Safety rule

Do not:

- pass `kUndiscovered` records to `Map.CreateMarkerIcon()`
- call `Map.ChangeMarkerState()` for testing
- increment region-summary quests
- mutate collectible completion state
- write synthetic save data
