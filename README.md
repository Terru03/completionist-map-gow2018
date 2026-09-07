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

## Current status: v0.9.6.1 test build

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
- Kratos's map marker has a session-local Hide/Show toggle while preserving stock Go-to-Journal behaviour.
- Hiding Kratos no longer changes the next map opening centre; the hidden transformed player marker remains the camera focus.
- Map zoom is extended from stock `MaxIn=6` to `MaxIn=2.5`.
- Distinct discovered DockPoint backing IDs are used for Raven, Nornir parents and Nornir puzzle actors, with field-confirmed `ALIAS_CHECK sameGO=false`.
- Raven map placement is independent of the currently tracked compass target.

### v0.9.5.1 field result

`Completionist-Map-v0.9.5.1-INSTALLER-FIX.zip` confirmed the hidden-Kratos centring fix and preserved filters/marker placement. It also disproved the attempted manual-hover coordinate path:

- `MANUAL_HOVER_CURSOR` reported UI-root positions around `0,-40.222,0`.
- custom map pins use map-space positions around `x=3.x`, `z=0.x`.
- no `MANUAL_HOVER active=true`, `NORNIR_CHEST_COMPASS`, `NORNIR_COMPASS` or `CUSTOM_COMPASS` event fired.
- the observed `BOAT DOCK - The Mason's Channel` and ~683 m HUD destination therefore came from a stock DockPoint selection, not the Completionist target.

### v0.9.6 / v0.9.6.1

Current test build:

`Completionist-Map-v0.9.6.1-INSTALLER-FIX.zip`

v0.9.6 changes:

- Returns to the field-proven v0.9.4 custom marker interaction model: synthetic markers are `UI.SetIsClickable()` and selected through `MapCollisionChangeHandler`.
- Removes the failed manual `MapCursor:GetWorldPosition()` proximity path.
- Disables the map camera's magnetic cursor attraction completely for this test:
  - `CursorSnap_Enabled=0`
  - `CursorSnap_Strength=0.0`
- Keeps custom marker visuals at native backing scale `1.0`.
- Clears any currently tracked stock compass marker before enabling Raven/Nornir custom tracking, so stale DockPoint destinations cannot remain on the HUD.
- Deactivates the custom target when a stock marker is selected later, keeping one compass destination active at a time.
- Retains hidden-Kratos centring, deep zoom `MaxIn=2.5`, filters and real completion lifecycle handling.

The first v0.9.6 installer aborted before writing the override because `PLAYER_HIDDEN_CENTER` was validated before the hidden-player regex replacement ran. v0.9.6.1 is an installer-order-only hotfix. No gameplay/marker/compass logic changed.

The next field test should verify that direct hover/collision still works with map-camera snap disabled, and that custom Raven/Nornir tracking no longer resolves to a stock Boat Dock destination.

## Icon system

Original Completionist artwork is already present on `dev` under `assets/icons/`.

Canonical source glyphs currently include:

- Raven
- Nornir Chest
- Nornir Seal
- Nornir Bell
- Nornir Mechanism
- Lore Marker
- Artefact
- Legendary Chest
- Generic Remaining
- Player/filter artwork

See [`docs/ICON-DESIGN-SYSTEM.md`](docs/ICON-DESIGN-SYSTEM.md). The current gameplay test build deliberately keeps the temporary DockPoint/HUD proof visuals until selection and compass routing are stable. Custom texture/material injection is the next isolated visual milestone.

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
