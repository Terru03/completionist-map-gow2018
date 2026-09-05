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
- `v0.2-diagnostic`: succeeded. Alfheim exposed 27 marker records on the current save, including 23 `kUndiscovered` records and 4 `kDiscovered` records, proving that hidden marker records are already available to Lua.
- `v0.3-diagnostic`: current development build. It probes Alfheim marker metadata, known flags, quest associations and scalar fields without creating icons or changing progression.

## Repository policy

The repository tracks our own patches, tooling, notes and diagnostic logic. Decompiled game source is intentionally not committed. Local builds should be generated from the player's own `mods/lua_source` files supplied by GoW Script Loader.

## Local paths used during testing

```text
G:\SteamLibrary\steamapps\common\GodOfWar\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua_source\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua\
```

## Current hypothesis

The game already gives the map layer stable hidden marker IDs. The preferred implementation path is therefore:

```text
native hidden marker -> identify collectible/type -> safely expose/select -> native compass navigation
```

rather than maintaining our own list of collectible coordinates.

## Next step

Run `v0.3-diagnostic`, open Alfheim once, then inspect `mods/loader_log.txt` for lines beginning with:

```text
[CompletionistMap v0.3]
```

We are specifically looking for marker metadata that lets us distinguish collectible-like hidden records and determine whether their native IDs can be fed into the existing waypoint/compass pipeline without changing their discovery state.
