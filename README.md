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

## Current status: v0.9.3.1 hotfix

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

### v0.9.2 result

The distinct-backing architecture was introduced successfully, but marker creation called `CompletionistMapV092_ApplyZoomAdaptiveIconScale` from functions defined before that helper's later local declaration. Those earlier closures resolved the helper as a nil global. Raven survived visually because its GameObject had already been stored/moved before the protected call failed, while Nornir parent/child creation recycled their failed GameObjects.

### v0.9.3 field regression

v0.9.3 attempted to remove the adaptive-scale experiment and tune snapping, but its map-side patch did not initialise at all. The field log contained Raven/Nornir gameplay instrumentation and the MainHUD hook but no `MAP_SCRIPT_LOADED`, `FILTER_MAPPING`, custom marker creation or Kratos toggle. The build is therefore superseded.

### v0.9.3.1

Current hotfix build:

`Completionist-Map-v0.9.3.1-MAP-LOAD-HOTFIX.zip`

It is intentionally rebuilt from the field-proven compile-good v0.9.2 map patch. The only marker-code correction is the safe lexical-scope fix:

```lua
local CompletionistMapV0931_ApplyZoomAdaptiveIconScale

-- earlier marker functions capture that local

CompletionistMapV0931_ApplyZoomAdaptiveIconScale = function(go)
  ...
end
```

No Raven/Nornir marker loop structure is rewritten in this hotfix.

It also keeps deep zoom at `MaxIn=2.5` and reduces close-zoom snapping much more aggressively:

- `CursorScale_Min = 0.12`
- `CursorSnap_Strength = 0.55`

Distinct DockPoint backing slots remain enabled for Raven, Nornir parents and Nornir puzzle actors.

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
