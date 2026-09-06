# Prototype version history

This file records every numbered Completionist Map test build produced so far. Test ZIPs themselves are intentionally **not** committed because the repository policy excludes generated archives and decompiled game source. The repository tracks the design, result and regression history instead.

## v0.1 to v0.5.1: discovery and collectible-state research

| Version | Build | Result |
| --- | --- | --- |
| v0.1 | `Completionist-Map-v0.1-TEST.zip` | Failed experiment. Exposing undiscovered native marker records directly crashed when opening the map. |
| v0.2 | `Completionist-Map-v0.2-DIAGNOSTIC.zip` | Read-only marker-table diagnostic. Proved hidden marker records are visible to Lua. |
| v0.3 | `Completionist-Map-v0.3-DIAGNOSTIC.zip` | Detailed Alfheim marker metadata/flag diagnostic. |
| v0.3.1 | `Completionist-Map-v0.3.1-DIAGNOSTIC.zip` | Midgard + complete-Alfheim comparison. Proved `kUndiscovered` is not a collectible discriminator. |
| v0.4 | `Completionist-Map-v0.4-DIAGNOSTIC.zip` | Region/realm summary correlation. Rejected the native hidden-marker table as a direct collectible source. |
| v0.5 | `Completionist-Map-v0.5-RAVEN-DIAGNOSTIC.zip` | Initial Raven gameplay-object probe. Installer failed safely because local source was absent. |
| v0.5.1 | `Completionist-Map-v0.5.1-RAVEN-DIAGNOSTIC.zip` | Pinned-source fallback added. Confirmed Veithurgard has three Raven gameplay objects with exact world XYZ and restored killed/alive state matching the region summary. |

## v0.6 to v0.6.5.1: world-to-map and first synthetic marker work

| Version | Build | Result |
| --- | --- | --- |
| v0.6 | `Completionist-Map-v0.6-API-TRANSFORM-PROTOTYPE.zip` | Solved Midgard world-to-map transform: `mapX = 0.004 * worldZ + 0.0625431`, `mapZ = -0.004 * worldX + 0.6101961`. |
| v0.6.1 | `Completionist-Map-v0.6.1-VISIBLE-PIN-PROTOTYPE.zip` | Borrowed/moved a discovered DockPoint visual to the Raven position. Proved arbitrary map placement. |
| v0.6.2 | `Completionist-Map-v0.6.2-CHILD-TRANSFORM-PROTOTYPE.zip` | Tried moving a mutable child of a duplicated DockPoint. DockPoint exposed no useful `untracked` child. |
| v0.6.3 | `Completionist-Map-v0.6.3-RADIUS-TEMPLATE-PROTOTYPE.zip` | Searched discovered `RadiusType` markers for a safer mutable visual template. |
| v0.6.4 | `Completionist-Map-v0.6.4-DIRECT-CAMERA-PROTOTYPE.zip` | Direct map-camera/marker interaction prototype while isolating native-map UI behaviour. |
| v0.6.5 | `Completionist-Map-v0.6.5-COMPASS-TARGET-PROTOTYPE.zip` | First compass-target prototype. Installer patch anchor failed on the user's mapmenu layout. |
| v0.6.5.1 | `Completionist-Map-v0.6.5.1-COMPASS-TARGET-PROTOTYPE.zip` | Installer fixed. Proved custom map reticle/prompt flow but native-marker coordinates were not a safe arbitrary compass target. |

## v0.7 to v0.7.8: custom HUD compass path

| Version | Build | Result |
| --- | --- | --- |
| v0.7 | `Completionist-Map-v0.7-CUSTOM-HUD-COMPASS-PROTOTYPE.zip` | Began custom HUD-compass rendering instead of unsafe synthetic `game.Compass.ShowMarker()`. |
| v0.7.1 | `Completionist-Map-v0.7.1-DOCK-PROXY-HUD-FIX.zip` | Refined DockPoint proxy/map behaviour and HUD target handling. |
| v0.7.2 | `Completionist-Map-v0.7.2-NEW-PIN-HUD-FIX.zip` | Iterated independent map-pin + custom-HUD target behaviour. |
| v0.7.3 | `Completionist-Map-v0.7.3-MAP-HUD-DISCOVERY.zip` | Diagnostic/research build for map and HUD object discovery. |
| v0.7.4 | `Completionist-Map-v0.7.4-DOCK-ICON-MAP-HUD.zip` | First DockPoint-icon map/HUD test; original installer had a PowerShell parsing failure. |
| v0.7.4.1 | `Completionist-Map-v0.7.4.1-DOCK-ICON-MAP-HUD.zip` | Installer-fixed v0.7.4 test. Map marker/selectable prompt worked, but native compass usage remained unsuitable. |
| v0.7.5 | `Completionist-Map-v0.7.5-NATIVE-COMPASS-INSTANCE.zip` | Tested native compass-instance approaches; confirmed they are not a safe general solution for arbitrary collectible XYZ. |
| v0.7.6 | `Completionist-Map-v0.7.6-HUD-FACTORY-RESEARCH.zip` | HUD factory/object research. |
| v0.7.7 | `Completionist-Map-v0.7.7-HUD-NATIVE-VISUAL.zip` | Found a safe HUD-native visual carrier and proved it can be moved along the compass. |
| v0.7.8 | `Completionist-Map-v0.7.8-RAVEN-LIFECYCLE.zip` | Raven milestone: correct target guided the player to a real remaining Raven; killing it automatically cleared the HUD target and subsequent map pin. |

## v0.8 to v0.8.7: Nornir discovery, hierarchy and lifecycle

| Version | Build | Result |
| --- | --- | --- |
| v0.8.0 | `Completionist-Map-v0.8.0-NORNIR-POSITION-DIAGNOSTIC.zip` | Resolved a Breakable Nornir chest and `sealBreakable01..03` to exact world XYZ. |
| v0.8.1 | `Completionist-Map-v0.8.1-NORNIR-SEAL-STATE.zip` | Added exact rune index and individual visual-state diagnostics; established how to identify a persisted broken Breakable seal. A calibration-labelled variant was also produced during this step. |
| v0.8.2 | `Completionist-Map-v0.8.2-NORNIR-MAP-HUD.zip` | First visible Nornir seal map/HUD prototype; gameplay and map contexts did not share the expected `_G` registry. |
| v0.8.3 | `Completionist-Map-v0.8.3-NORNIR-REGISTRY-FIX.zip` | Added cross-context bridge/fallback. Verified chest/seal map coordinates can be rendered independently of native collectible markers. |
| v0.8.4 | `Completionist-Map-v0.8.4-NORNIR-COMPASS-ZOOM.zip` | Fixed a MainHUD cross-context registry crash and added extended map zoom (`MaxIn 6 -> 3.5`). |
| v0.8.5 | `Completionist-Map-v0.8.5-NORNIR-HIERARCHY-FILTERS.zip` | Added Nornir parent/child hierarchy and Completionist filter modes; map-side `MapOn:Update` injection had an extra `end` and prevented the map override from initialising. |
| v0.8.6 | `Completionist-Map-v0.8.6-MAP-FILTER-FIX.zip` | Fixed map-side load. Filters, parent marker and only-unbroken Breakable seals appeared. Nornir Add-to-Compass exposed a Lua lexical-scope bug. |
| v0.8.7 | `Completionist-Map-v0.8.7-NORNIR-COMPASS-FIX.zip` | Forward-declared the Nornir registry helper; parent Add-to-Compass no longer crashed. |

## v0.9 to current: native-feeling interaction and UX

| Version | Build | Result |
| --- | --- | --- |
| v0.9.0 | `Completionist-Map-v0.9.0-NORNIR-LIFECYCLE-NATIVE-HOVER.zip` | Larger lifecycle milestone: reveal puzzle siblings after locked-chest interaction, observe the authoritative standard Runic chest `OnOpened`, remove custom `Camera.PointAt` hover recentering, and use the native selected-cursor animation. Initial installer validation ran too early. |
| v0.9.0.1 | `Completionist-Map-v0.9.0.1-INSTALLER-FIX.zip` | Installer-order fix; v0.9.0 milestone logic then tested successfully. |
| v0.9.1 | `Completionist-Map-v0.9.1-SEAL-COMPASS-ZOOM-PLAYER.zip` | Seal Add-to-Compass confirmed. Deep zoom increased to `MaxIn=2.5`. Added session-local Hide/Show Kratos map-marker toggle. Remaining visual issue: multiple synthetic types reused the same DockPoint backing ID. |
| v0.9.2 | `Completionist-Map-v0.9.2-DISTINCT-BACKINGS-SNAP.zip` | Introduced distinct discovered DockPoint backing IDs and attempted tighter snap/adaptive scaling. **Field regression:** Raven survived, but Nornir parent/children were recycled because `CompletionistMapV092_ApplyZoomAdaptiveIconScale` was referenced before declaration and resolved as nil. |
| v0.9.3 | `Completionist-Map-v0.9.3-NORNIR-SNAP-FIX.zip` | **Current test build.** Removes the broken adaptive-scale experiment, keeps distinct backing IDs, restores Nornir marker creation, keeps `MaxIn=2.5`, and tightens close-zoom snapping through stock camera parameters: `CursorScale_Min=0.18`, `CursorSnap_Strength=0.9`. |

## Current invariants

The ordinary test path must remain save-safe:

- no `Map.ChangeMarkerState()` on synthetic/borrowed targets;
- no synthetic `game.Compass.ShowMarker()` for arbitrary collectible XYZ;
- no artificial region-summary increments;
- no collectible/puzzle completion mutation;
- no synthetic save writes.

The custom compass target is a UI-only bearing toward stored world XYZ. Gameplay scripts are instrumented only to observe the game's own restored/completed state and to clear UI markers when the underlying object is genuinely completed.
