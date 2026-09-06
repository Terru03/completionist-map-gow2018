# Completionist Map for God of War (2018)

Private development repository for a PC mod that exposes remaining collectible locations on the native God of War map and, where possible, allows the stock waypoint/compass navigation to guide the player to them.

## Target

- Game: God of War (2018), PC / Steam
- Steam App ID: `1593500`
- Tested game Build ID: `11168363`
- Loader: GoW Script Loader & Gameplay Tweaks `0.22`

## Goal

Preferred final behaviour:

1. Show only remaining collectibles.
2. Use native map markers rather than an external overlay.
3. Allow selecting a revealed collectible as a normal waypoint.
4. Use the existing compass/navigation system to guide the player to it.
5. Add filters/toggles so the feature can be disabled or limited by collectible type.

## Current status

- `v0.1-test`: attempted to expose undiscovered marker records directly. Opening the map crashed the game. Retained only as a failed experiment/reference.
- `v0.2-diagnostic`: proved hidden native marker records are exposed to Lua.
- `v0.3.1-diagnostic`: proved `kUndiscovered` is not a collectible filter. Midgard exposed 318 marker records, including 244 hidden records dominated by quest, dock, fight and travel infrastructure.
- `v0.4-diagnostic`: decisive negative for collectible-specific native map markers. Midgard is at 148/225 realm-summary progress, yet all 244 hidden native marker records returned `candidateFlags=<none>` for the collectible categories we tested.
- `v0.5.1-raven-registry`: successful gameplay-object correlation. A targeted Veithurgard test loaded exactly three Raven objects from `WAD_Xpl200_Funeral`: two restored as killed and one alive, exactly matching the region summary of 2/3 Ravens. Exact world coordinates were available for every object.
- `v0.6`: current development direction. Build an asset-derived collectible coordinate catalogue, then prove that an arbitrary collectible world position can be represented as a selectable map marker and compass/navigation target.

## Repository policy

The repository tracks our own patches, tooling, notes and diagnostic logic. Decompiled game source is intentionally not committed.

## Local paths used during testing

```text
G:\SteamLibrary\steamapps\common\GodOfWar\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua_source\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua\
```

## Architecture findings

The native map marker table is useful for ordinary POIs and stock compass navigation, but collectible completion is tracked separately.

The actual gameplay scripts retain the data we need:

- Ravens: `thisObj`, `ravenKilled`, `regionSummaryQuest`, `thisObj:GetWorldPosition()`
- Artefacts: `thisObj`, acquisition `state`, `regionSummaryQuest`
- Lore markers/rune reads: `thisObj`, `mapSummaryComplete`, `regionSummaryQuest`
- Pocket rifts: `thisObj`, `hasOpened`, `regionSummaryQuest`
- Standard chests: `thisObj`, `state`, `ChestType`, `WADName`, region-summary updates for `LegendaryChest` and `RunicChest`

The targeted Veithurgard Raven test proved two things simultaneously:

1. restored per-object completion state is trustworthy: the three live objects reported `2 killed + 1 alive`, matching the map summary's `2 / 3`;
2. collectible scripts are streamed by local WAD rather than instantiated realm-wide, because `precisionchallenge.lua` only loaded after entering the target area.

Known remaining Raven from that test:

```text
WAD: WAD_Xpl200_Funeral
region summary quest: RegionSummary_VF_Raven_Parent
x: -64.850898742676
y: 12.987384796143
z: 787.30694580078
state on test save: alive
```

The stock map's normal waypoint flow ultimately calls:

```lua
game.Compass.ShowMarker(markerID, markerType)
```

for recognised map-marker IDs. The remaining technical problem is creating or emulating a marker that is backed by an arbitrary collectible world position rather than an existing stock POI marker.

## Current implementation path

```text
game assets / collectible objects
    -> generated coordinate catalogue
    -> live save/progression state
    -> remaining collectible set
    -> custom/native-compatible map icon
    -> compass/navigation target
```

Runtime object instrumentation remains useful for validating catalogue coordinates and state semantics, but it cannot discover the entire realm immediately because unloaded WADs do not instantiate their collectible scripts.

## Next step

Issue #5 tracks `v0.6`:

1. determine how the map converts world coordinates into map-space;
2. determine whether Lua can create a synthetic native marker/compass target;
3. if not, prototype a UI-only map marker plus separate compass target;
4. use the known remaining Veithurgard Raven as the first end-to-end test point;
5. begin extracting/recording coordinates for Ravens, Artifacts, Lore Markers, Runic Chests, Legendary Chests and Pocket Rifts.
