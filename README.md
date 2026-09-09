# Completionist Map for God of War (2018)

Private development repository for a PC mod that exposes remaining collectible locations on the native God of War map and lets Completionist markers participate in the game's native compass routing.

## Target

- Game: God of War (2018), PC / Steam
- Steam App ID: `1593500`
- Tested game Build ID: `11168363`
- Loader: GoW Script Loader & Gameplay Tweaks `0.22`

## Goal

Preferred final behaviour:

1. Show only remaining collectibles.
2. Use the native map UI rather than an external overlay.
3. Allow selecting a collectible and tracking it through the native HUD compass.
4. Preserve native distance, route/pathfinding, Add/Replace/Remove semantics, and the one-active-target rule.
5. Add native-feeling filter modes for collectible families.
6. Hide completed objects immediately and correctly restore their state after reload.
7. Ship dedicated God of War-style map, HUD and in-world artwork for Completionist markers.

## Current status: v0.10.4 Raven native pipeline proven

The first full native Completionist marker architecture is now runtime-proven for an Odin's Raven.

`Completionist_V103_Veithurgard_Raven_01` has been tested successfully with:

- custom Raven map artwork;
- custom Raven compass HUD artwork;
- custom Raven floating in-world artwork;
- native distance;
- native compass graph/pathfinding;
- Add to Compass;
- stock marker -> Raven replacement;
- Raven -> stock marker replacement;
- Remove from Compass;
- exactly one active user target;
- no crash.

The definitive field result is archived in:

`archive/field-logs/completionist-v104-raven-full-compass-runtime-success.json`

The Raven production architecture is documented in:

[`docs/builds/v0.10.4-raven-native-production.md`](docs/builds/v0.10.4-raven-native-production.md)

### Proven Raven resource layout

```text
Completionist authored Raven marker
    -> CompletionistRaven CompassIconClass
    -> native mapcoords + compassgraph
    -> map: goMapIconCompletionistRaven
    -> HUD: goCompletionistRavenHUD
    -> in-world: COMPASS_INWORLD_COMPLETIONIST_RAVEN
                    -> goCompletionistRavenHUD
```

Important implementation findings:

- custom HUD GameObjects must be present in `r_ui.wad` and registered in `WAD_R_UI.GOPool`;
- `goCompletionistRavenHUD` must have GOPool capacity `2`, because the compass and floating in-world marker can require two simultaneous instances;
- the custom compass class needs its own live-manager query for Raven add/remove because the stock enabled-class list does not contain `CompletionistRaven`;
- stock-origin compass actions remain delegated to the game, preserving native Replace in Compass behavior;
- a dedicated type-`0x129` in-world carrier can reuse the same custom HUD visual without modifying the real DockPoint resources.

## Production handoff

Research A/B layers are being consolidated into a reusable native-marker production pipeline on `codex/v104-raven-production`.

The current proven installation can be verified and adopted without rewriting the game:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\v0.10.4\verify-raven-production-state.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\v0.10.4\adopt-raven-production-state.ps1"
```

Both commands require God of War to be closed. Verification is read-only. Adoption writes only an ignored local manifest under `build/`.

The reusable marker contract is defined in:

- `data/native-markers/schema.json`
- `data/native-markers/raven.json`

The next collectible family must be added from that contract without weakening the Raven runtime invariants.

## Other collectible research already available

Earlier versions established useful state/lifecycle work that remains relevant while those families are migrated to the native architecture:

- Raven gameplay objects expose exact XYZ and restored killed/alive state.
- Midgard world-to-map transform is solved:
  - `mapX = 0.004 * worldZ + 0.0625431`
  - `mapZ = -0.004 * worldX + 0.6101961`
- Breakable Nornir chests expose their chest parent and three seal GameObjects with exact XYZ.
- Persisted already-broken Breakable seals can be distinguished and omitted.
- Trying a locked Nornir chest reveals its remaining puzzle siblings.
- Opening the real Runic chest is observed from `interact_chest_standard.lua::OnOpened()` and removes the Completionist parent marker.
- Custom map filters and completion lifecycle prototypes have already been field-tested.

Those older synthetic-marker/HUD experiments are historical research, not the target architecture for new production marker families.

## Icon system

Original Completionist artwork is stored under `assets/icons/`.

Canonical source/concept glyphs include:

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

See [`docs/ICON-DESIGN-SYSTEM.md`](docs/ICON-DESIGN-SYSTEM.md).

## Version history

Prototype and field-test history is documented in [`docs/VERSION_HISTORY.md`](docs/VERSION_HISTORY.md) and `docs/builds/`. Generated ZIPs are deliberately not committed.

## Repository policy

The repository tracks our own patches, tooling, notes, icon assets, marker specifications and diagnostic logic. Decompiled/proprietary game source and generated test ZIPs are intentionally not committed.

## Local paths used during testing

```text
G:\SteamLibrary\steamapps\common\GodOfWar\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua_source\
G:\SteamLibrary\steamapps\common\GodOfWar\mods\lua\
```

## Architecture

The production target is now native-marker-first:

```text
asset-derived collectible catalogue
    + restored live/save completion state
    -> remaining collectible set
    -> authored Completionist native marker
    -> dedicated Completionist CompassIconClass
    -> native mapcoords + compassgraph
    -> dedicated map visual
    -> dedicated HUD visual
    -> dedicated in-world carrier
    -> stock single-target compass semantics
```

Gameplay-object instrumentation remains important for validating completion semantics, but unloaded WADs do not instantiate every collectible realm-wide. The complete catalogue therefore needs an asset-derived/static component reconciled against live/save state.

## Safety rules

Normal production work must not:

- mutate collectible or puzzle completion state merely to expose a marker;
- increment region-summary completion artificially;
- overwrite stock DockPoint resources globally;
- weaken the one-active-compass-target invariant;
- replace native route/pathfinding with a fake relative-direction HUD target when native data is available;
- write synthetic save data.
