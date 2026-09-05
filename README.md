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
- `v0.4-diagnostic`: current development build. Correlates Midgard's realm/region completion summaries with hidden marker records and safely tests collectible-category flag names without rendering anything.

## Repository policy

The repository tracks our own patches, tooling, notes and diagnostic logic. Decompiled game source is intentionally not committed. Local builds should be generated from the player's own `mods/lua_source` files supplied by GoW Script Loader.

## Local paths used during testing

```text
G:\SteamLibrary\steamapps\common\GodOfWar\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua_source\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua\
```

## Current hypothesis

The map-marker table contains useful native POI/navigation records, but collectible progression appears to be tracked separately through region-summary categories and gameplay-object state.

The preferred implementation path is now conditional:

```text
if collectible-specific native marker exists:
    native collectible marker -> reveal safely -> stock compass
else:
    remaining collectible gameplay object -> world position -> custom/native-compatible map marker -> stock compass
```

## Next step

Run `v0.4-diagnostic`, open Midgard once, then inspect `mods/loader_log.txt` for lines beginning with:

```text
[CompletionistMap v0.4]
```

The decisive questions are:

1. Which Midgard regions/categories are actually incomplete on the current save?
2. Do any hidden marker records carry collectible flags such as `LoreMarker`, `Ravens`, `RunicChest` or `LegendaryChest`?
3. If not, which gameplay-object/pickup path should be used to obtain exact world positions for remaining collectibles?
