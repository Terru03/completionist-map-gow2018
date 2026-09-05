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

- `v0.1-test`: attempted to expose undiscovered marker records directly. Opening the map crashed the game. This build is retained only as a failed experiment/reference.
- `v0.2-diagnostic`: safe diagnostic approach. It does not create additional icons. It logs marker records returned by `Map.GetMarkersInfoTable(regionId)` so we can determine what the game exposes for undiscovered collectibles before touching icon creation again.

## Repository policy

The repository tracks our own patches, tooling, notes and diagnostic logic. Decompiled game source is intentionally not committed. Local builds should be generated from the player's own `mods/lua_source` files supplied by GoW Script Loader.

## Local paths used during testing

```text
G:\SteamLibrary\steamapps\common\GodOfWar\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua_source\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua\
```

## Next step

Run `v0.2-diagnostic`, open Alfheim on the map, then inspect `mods/loader_log.txt` for lines beginning with:

```text
[CompletionistMap v0.2]
```

The important question is whether Alfheim's marker table contains useful `kUndiscovered` records and whether those records contain stable IDs that can be resolved to positions or native waypoint objects without calling the normal discovered-marker icon path.
