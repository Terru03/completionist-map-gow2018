# Completionist Map for God of War (2018)

Private development repository for a PC mod that exposes remaining collectible locations on the native God of War map and provides a custom HUD-compass bearing to arbitrary collectible world positions.

## Target

- Game: God of War (2018), PC / Steam
- Steam App ID: `1593500`
- Tested game Build ID: `11168363`
- Loader: GoW Script Loader & Gameplay Tweaks `0.22`

## Goal

Preferred final behaviour:

1. Show only remaining collectibles.
2. Use the native map UI rather than an external overlay.
3. Allow selecting a collectible and tracking it on the HUD compass.
4. Add native-feeling filter modes for collectible families.
5. Hide completed objects immediately and correctly restore their state after reload.
6. Ship dedicated God of War-style artwork for Completionist markers.

## Current status: v0.9.4 test build

The project has progressed beyond the original hidden-native-marker approach. Collectibles are tracked by their gameplay scripts/state, converted from world XYZ into Midgard map coordinates, and represented by synthetic native-compatible UI pins.

Confirmed working milestones:

- Odin's Raven gameplay objects expose exact XYZ and restored killed/alive state.
- Midgard world-to-map transform is solved:
  - `mapX = 0.004 * worldZ + 0.0625431`
  - `mapZ = -0.004 * worldX + 0.6101961`
- A remaining Raven can be placed on the map and tracked by the custom HUD compass.
- Killing the Raven automatically clears the HUD target and suppresses its later map pin.
- Breakable Nornir chests expose their chest parent and three seal GameObjects with exact XYZ.
- Persisted already-broken Breakable seals can be distinguished and omitted.
- Trying a locked Nornir chest reveals its remaining puzzle siblings.
- Opening the real Runic chest is observed from `interact_chest_standard.lua::OnOpened()` and removes the Completionist parent marker.
- Custom map filters are appended to the existing bottom-left filter cycle:
  - `COMPLETIONIST`
  - `RAVENS`
  - `NORNIR CHESTS`
  - `NORNIR PUZZLE`
- Seal Add-to-Compass works through the custom arbitrary-XYZ HUD target.
- Kratos's map marker has a session-local Hide/Show toggle when the stock Go-to-Journal action is not using that button.
- Map zoom is extended from stock `MaxIn=6` to `MaxIn=2.5`.
- Distinct discovered DockPoint backing IDs are used for Raven, Nornir parents and Nornir puzzle actors, with field-confirmed `ALIAS_CHECK sameGO=false`.

### v0.9.3.1 field result

`Completionist-Map-v0.9.3.1-MAP-LOAD-HOTFIX.zip` successfully restored the full map-side stack after the v0.9.3 regression. The test confirmed:

- `MAP_SCRIPT_LOADED` and 11-entry filter mapping;
- Raven, Nornir parent and only-remaining seal pins;
- custom chest/seal compass tracking;
- Hide/Show Kratos;
- real chest-open removal;
- distinct synthetic GameObjects.

It also exposed two remaining UX bugs:

1. Raven placement still read the single shared `_G.CompletionistMap...Target.mapX/mapZ`. Tracking a Nornir chest therefore moved the Raven map pin onto the Nornir position until the active target changed again.
2. Synthetic DockPoint roots remained too large/sticky for the newly extended close zoom. The field log showed `SNAP_TUNING cursorScale=1 customIconScale=1`, so the intended adaptive shrink never occurred.

### v0.9.4

Current test build:

`Completionist-Map-v0.9.4-RAVEN-SNAP-FIX.zip`

Changes:

- Raven map coordinates are immutable and no longer derived from the active compass target.
- Nornir chest/seal tracking can no longer move or hide the Raven pin.
- Temporary synthetic marker roots use fixed scale `0.28` to shrink their visible/clickable footprint.
- Nornir child collision latch is reduced from `120` to `12` frames.
- Deep zoom remains `MaxIn=2.5`.
- Snap tuning is reduced further:
  - `CursorScale_Min = 0.05`
  - `CursorSnap_Strength = 0.18`

The next field test should specifically verify Raven remains in place while Nornir is tracked and that close-zoom snapping is materially less aggressive.

## Version history

Every numbered prototype/test build is documented in [`docs/VERSION_HISTORY.md`](docs/VERSION_HISTORY.md). Generated ZIPs are deliberately not committed.

## Repository policy

The repository tracks our own patches, tooling, notes and diagnostic logic. Decompiled/proprietary game source and generated test ZIPs are intentionally not committed.

## Local paths used during testing

```text
G:\SteamLibrary\steamapps\common\GodOfWar\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua_source\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua\
```

## Architecture

The native hidden map-marker table is not the collectible database. The practical architecture is:

```text
game assets / collectible gameplay objects
    -> identity + WAD + region + world position
    -> restored live completion state
    -> remaining collectible set
    -> world-to-map transform
    -> synthetic/native-compatible map UI pin
    -> custom HUD compass bearing to arbitrary world XYZ
```

Gameplay-object instrumentation remains valuable for validating state semantics, but unloaded WADs do not instantiate every collectible realm-wide. The final catalogue therefore needs an asset-derived/static component reconciled against live/save state.

## Safety rules

Normal testing must not:

- call `Map.ChangeMarkerState()` for Completionist pins;
- call synthetic `game.Compass.ShowMarker()` for arbitrary collectible XYZ;
- increment region-summary completion artificially;
- mutate puzzle or collectible completion state;
- write synthetic save data.
