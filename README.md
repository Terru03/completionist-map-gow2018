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
- `v0.5-raven-registry`: current development build. It patches the user's exact local `precisionchallenge.lua` and logs live Odin's Raven objects, restored killed state, region-summary quest and world X/Y/Z. The key question is whether all/most Midgard ravens instantiate at load time or only ravens in currently loaded WADs.

## Repository policy

The repository tracks our own patches, tooling, notes and diagnostic logic. Decompiled game source is intentionally not committed. Local builds are generated from the player's own `mods/lua_source` files supplied by GoW Script Loader.

## Local paths used during testing

```text
G:\SteamLibrary\steamapps\common\GodOfWar\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua_source\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua\
```

## Architecture finding

The native map marker table is useful for ordinary POIs and stock compass navigation, but collectible completion is tracked separately.

The actual gameplay scripts retain the data we need:

- Ravens: `thisObj`, `ravenKilled`, `regionSummaryQuest`, `thisObj:GetWorldPosition()`
- Artefacts: `thisObj`, acquisition `state`, `regionSummaryQuest`
- Lore markers/rune reads: `thisObj`, `mapSummaryComplete`, `regionSummaryQuest`
- Pocket rifts: `thisObj`, `hasOpened`, `regionSummaryQuest`
- Standard chests: `thisObj`, `state`, `ChestType`, `WADName`, region-summary updates for `LegendaryChest` and `RunicChest`

The stock map also exposes `game.Compass.ShowMarker(markerID, markerType)` for normal map POIs. Once collectible positions and remaining-state detection are solved, the next UI problem is creating a native-compatible selectable marker/compass target without touching completion state.

## Current implementation path

```text
actual collectible object
    -> exact remaining/completed state
    -> exact world position
    -> Completionist Map registry
    -> custom/native-compatible map icon
    -> compass/navigation target
```

The current uncertainty is object lifetime. If the game instantiates collectibles across the whole realm, the registry can be built entirely at runtime. If it only instantiates objects from loaded WADs, we will need an asset-derived coordinate cache or another way to enumerate unloaded world objects.

## Next step

Run `v0.5-raven-registry` on a Midgard save and capture lines beginning with:

```text
[CompletionistMap v0.5] RAVEN
```

If the count approaches Midgard's 43 raven objects, runtime registration is viable. If only a small local subset appears, pivot to offline WAD/object extraction while still deriving positions from the game's own assets.
