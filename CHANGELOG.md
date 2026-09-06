# Changelog

For the exhaustive numbered prototype list, including superseded and failed test builds, see [`docs/VERSION_HISTORY.md`](docs/VERSION_HISTORY.md).

## v0.9.4-raven-snap-fix

- Field result from v0.9.3.1 confirmed the full map-side stack was healthy again: filters, Raven/Nornir pins, custom compass, Kratos toggle and real Nornir chest-open removal all worked.
- Fixes Raven/Nornir target interference. Raven map placement no longer reads the single shared active compass target's `mapX/mapZ`; it uses immutable Raven map coordinates instead.
- Adds `RAVEN_PIN_INDEPENDENT` diagnostic to prove Raven stays at its own map coordinate while a Nornir chest/seal is tracked.
- Replaces ineffective adaptive root scaling (`cursorScale=1`, `customIconScale=1` in field logs) with fixed synthetic root scale `0.28`.
- Reduces Nornir child selection latch from `120` to `12` frames.
- Tightens close-zoom snap further:
  - `CursorScale_Min: 0.12 -> 0.05`
  - `CursorSnap_Strength: 0.55 -> 0.18`
- Retains deep zoom `MaxIn=2.5`, distinct backing IDs, custom filters, seal Add-to-Compass and Hide/Show Kratos.

## v0.9.3.1-map-load-hotfix

- Field result from v0.9.3 showed **no map-side Completionist startup at all**: `MAP_SCRIPT_LOADED`, `FILTER_MAPPING`, custom marker creation and `PLAYER_MARKER_TOGGLE` were all absent.
- Rebuilds from the field-proven compile-good v0.9.2 map patch instead of stacking more structural edits onto v0.9.3.
- Fixes the v0.9.2 adaptive-scale nil helper with the safe Lua pattern already used elsewhere: forward-declare `CompletionistMapV0931_ApplyZoomAdaptiveIconScale`, then assign its implementation later.
- Leaves the v0.9.2 Raven/Nornir marker loops structurally unchanged.
- Retains distinct discovered DockPoint backing IDs for Raven, Nornir parent and Nornir puzzle pins.
- Keeps deep map zoom at `MaxIn=2.5`.
- Reduces close-zoom snapping:
  - `CursorScale_Min: 0.50 -> 0.12`
  - `CursorSnap_Strength: 2.4 -> 0.55`
- Retains custom filters, seal Add-to-Compass and Hide/Show Kratos.
- Field result: successful recovery. `ALIAS_CHECK` reported distinct GameObjects, but Raven still moved to a Nornir target because its reinforcement used the shared compass-target coordinates. Snapping also remained too aggressive.

## v0.9.3-nornir-snap-fix

- Intended to fix the v0.9.2 marker-creation regression and tighten snapping.
- **Field regression:** map-side Completionist code did not initialise at all. The log contained gameplay/HUD instrumentation but no `MAP_SCRIPT_LOADED`, `FILTER_MAPPING`, custom markers or Kratos toggle.
- Superseded by v0.9.3.1, which is rebuilt from v0.9.2 rather than modifying the broken v0.9.3 map structure.

## v0.9.2-distinct-backings-snap

- Introduced a pool of distinct discovered Midgard DockPoint backing IDs rather than reusing one marker ID for all synthetic pins.
- Added `BACKING_POOL`, `BACKING_ASSIGN` and `ALIAS_CHECK` diagnostics.
- Attempted zoom-adaptive synthetic marker scaling.
- Field result: Raven remained visible, but Nornir parent/children disappeared because the scale helper resolved as a nil global during creation.

## v0.9.1-seal-compass-zoom-player

- Confirmed Nornir seal Add-to-Compass: `NORNIR_PROMPT -> NORNIR_COMPASS -> HUD_NORNIR_TRACK`.
- Gives puzzle children collision priority over their parent chest and keeps a short selection latch.
- Extends map zoom to `MaxIn=2.5`.
- Adds session-local Hide/Show Kratos map-marker toggle while preserving stock Go-to-Journal behaviour.

## v0.9.0.1-installer-fix

- Fixes v0.9.0 installer validation ordering. The milestone logic was valid, but the installer checked for the injected native-hover path before applying that injection.

## v0.9.0-nornir-lifecycle-native-hover

- Removes custom `Camera.PointAt()` marker hover recentering so custom hover preserves zoom.
- Uses the stock selected-cursor animation path.
- Reveals remaining Nornir puzzle siblings after the locked chest is attempted/restored as locked.
- Observes `interact_chest_standard.lua::OnOpened()` as the authoritative Runic chest-open event.
- Clears/removes the Nornir parent only after the real loot chest is opened.

## v0.8.7-nornir-compass-fix

- Fixes Lua lexical scope for `CompletionistMap...GetNornirRegistry` by forward-declaring the local helper before `IsTargetCollected()` captures it.

## v0.8.6-map-filter-fix

- Fixes the premature `end` in the v0.8.5 `MapOn:Update()` injection.
- Restores map-side Completionist loading, Raven/Nornir pins and custom filter mapping.
- Correctly omits persisted broken Breakable seals.

## v0.8.5-nornir-hierarchy-filters

- Introduces top-level Nornir chest parents versus child puzzle actors.
- Adds Completionist-specific logical filters into the existing bottom-left filter cycle.
- Field result: map-side injection failed because `MapOn:Update()` was closed early.

## v0.8.4-nornir-compass-zoom

- Removes a MainHUD call to a map-only Nornir registry helper.
- Tracks selected Nornir targets directly by copied world XYZ.
- Adds extended map zoom (`MaxIn 6 -> 3.5`).

## v0.8.3-nornir-registry-fix

- Fixes map/gameplay context isolation by adding a cross-context bridge and a verified-coordinate fallback for the known Breakable chest.
- Makes synthetic Nornir map pins independent of shared `_G` state for the tested chest.

## v0.8.2-nornir-map-hud

- First visible synthetic Nornir map/HUD prototype.
- Field result exposed that gameplay and map scripts did not share the assumed plain `_G` registry.

## v0.8.1-nornir-seal-state

- Adds exact `runeIndex` and individual rune visual-state diagnostics.
- Establishes persisted Breakable seal suppression semantics.

## v0.8.0-nornir-position-diagnostic

- Resolves `sealBreakable01..03` GameObjects to exact world XYZ for a real Breakable Nornir chest.

## v0.7.8-raven-lifecycle

- Raven milestone: map target led to a real remaining Raven.
- Killing the Raven cleared the custom HUD target and suppressed its later map marker.

## v0.7.x custom-HUD research

- Iterated away from unsafe synthetic native compass markers.
- Proved a HUD-native visual can be repositioned along the compass according to an arbitrary stored world XYZ bearing.
- See `docs/VERSION_HISTORY.md` for v0.7 through v0.7.7 individually.

## v0.6-api-transform-prototype

- Confirmed native marker records expose world-space `Coordinates`.
- Solved Midgard world-to-map transform:
  - `mapX = 0.004 * worldZ + 0.0625431`
  - `mapZ = -0.004 * worldX + 0.6101961`
- Maximum observed residual was approximately `1.2e-7` map units.

## v0.5.1-raven-registry-diagnostic

- Validates/deploys a pinned Raven gameplay-script reference when local source is missing.
- Confirms three Veithurgard Raven objects: two killed and one alive, matching the region summary.
- Captures exact remaining Raven world XYZ.

## v0.4-diagnostic

- Correlates realm/region completion summaries with hidden marker records.
- Rejects the native hidden-marker table as the direct collectible source.

## v0.3.1-diagnostic

- Uses incomplete Midgard against 100%-complete Alfheim as control.
- Proves `kUndiscovered` is dominated by infrastructure and is not a collectible state.

## v0.2-diagnostic

- Proves hidden marker records are exposed to Lua without rendering them.

## v0.1-test

- First hidden-marker rendering experiment.
- Opening the map crashed; direct rendering of arbitrary undiscovered native records was abandoned.
