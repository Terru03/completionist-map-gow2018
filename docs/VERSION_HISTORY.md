# Prototype version history

This file records every numbered Completionist Map test build produced so far. Test ZIPs themselves are intentionally **not** committed because the repository policy excludes generated archives and decompiled game source. The repository tracks the design, result and regression history instead.

## v0.10: custom icon pipeline

| Version | Build | Result |
| --- | --- | --- |
| v0.10.0 | `Completionist-Map-v0.10.0-ICON-PIPELINE.zip` | **Current test build.** Built from the stable v0.9.6.1 behaviour. Installer fetches all ten user-authored concept PNG masters from `feat/completionist-icon-system`, generates 24/32/48/64 px transparent production candidates and writes a SHA256/dimension manifest under `mods/completionist-map/icons`. Synthetic Raven/Nornir map duplicates probe for undocumented direct `SetTexture` / `SetImage` style APIs and attempt a loose-PNG binding only if such a method is actually exposed. HUD carrier is capability-probed only. If the engine exposes no direct loose-PNG binding, stable DockPoint/HUD proof visuals remain and `ICON_CAPS` / `ICON_BIND_*` identify the next authored-material/texpack integration route. |

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
| v0.8.2 | `Completionist-Map-v0.8.2-NORNIR-MAP-HUD.zip` | First visible synthetic Nornir seal map/HUD prototype; gameplay and map contexts did not share the expected `_G` registry. |
| v0.8.3 | `Completionist-Map-v0.8.3-NORNIR-REGISTRY-FIX.zip` | Added cross-context bridge/fallback. Verified chest/seal map coordinates can be rendered independently of native collectible markers. |
| v0.8.4 | `Completionist-Map-v0.8.4-NORNIR-COMPASS-ZOOM.zip` | Fixed a MainHUD cross-context registry crash and added extended map zoom (`MaxIn 6 -> 3.5`). |
| v0.8.5 | `Completionist-Map-v0.8.5-NORNIR-HIERARCHY-FILTERS.zip` | Added Nornir parent/child hierarchy and Completionist filter modes; map-side `MapOn:Update` injection had an extra `end` and prevented the map override from initialising. |
| v0.8.6 | `Completionist-Map-v0.8.6-MAP-FILTER-FIX.zip` | Fixed map-side load. Filters, parent marker and only-unbroken Breakable seals appeared. Nornir Add-to-Compass exposed a Lua lexical-scope bug. |
| v0.8.7 | `Completionist-Map-v0.8.7-NORNIR-COMPASS-FIX.zip` | Forward-declared the Nornir registry helper; parent Add-to-Compass no longer crashed. |

## v0.9: native-feeling interaction and UX

| Version | Build | Result |
| --- | --- | --- |
| v0.9.0 | `Completionist-Map-v0.9.0-NORNIR-LIFECYCLE-NATIVE-HOVER.zip` | Larger lifecycle milestone: reveal puzzle siblings after locked-chest interaction, observe the authoritative standard Runic chest `OnOpened`, remove custom `Camera.PointAt` hover recentering, and use the native selected-cursor animation. Initial installer validation ran too early. |
| v0.9.0.1 | `Completionist-Map-v0.9.0.1-INSTALLER-FIX.zip` | Installer-order fix; v0.9.0 milestone logic then tested successfully. |
| v0.9.1 | `Completionist-Map-v0.9.1-SEAL-COMPASS-ZOOM-PLAYER.zip` | Seal Add-to-Compass confirmed. Deep zoom increased to `MaxIn=2.5`. Added session-local Hide/Show Kratos map-marker toggle. Remaining visual issue: multiple synthetic types reused the same DockPoint backing ID. |
| v0.9.2 | `Completionist-Map-v0.9.2-DISTINCT-BACKINGS-SNAP.zip` | Introduced distinct discovered DockPoint backing IDs and attempted tighter snap/adaptive scaling. Field regression: Raven survived, but Nornir parent/children were recycled because `CompletionistMapV092_ApplyZoomAdaptiveIconScale` was referenced before declaration and resolved as nil. |
| v0.9.3 | `Completionist-Map-v0.9.3-NORNIR-SNAP-FIX.zip` | Attempted to remove the v0.9.2 adaptive-scale regression. **Field regression:** map-side Completionist code did not initialise at all; no custom markers, filters or Kratos toggle. Superseded. |
| v0.9.3.1 | `Completionist-Map-v0.9.3.1-MAP-LOAD-HOTFIX.zip` | Successful recovery build. Map, filters, Kratos toggle, Raven, Nornir parent/seals and custom compass all loaded. Field result exposed two UX bugs: Raven placement still read the single shared compass target, and synthetic marker snapping remained too aggressive. |
| v0.9.4 | `Completionist-Map-v0.9.4-RAVEN-SNAP-FIX.zip` | Fixed Raven/Nornir target interference and field-confirmed `RAVEN_PIN_INDEPENDENT`. Raven, chest/seals, filters, compass and Kratos toggle all worked. Remaining UX issues: hidden Kratos caused the next map open to use the central fallback, custom pins still had a strong long-range cursor magnet, and scale `0.28` made them visibly smaller than native markers. |
| v0.9.5 | `Completionist-Map-v0.9.5-NO-MAGNET-HOVER.zip` | Attempted to remove native clickability and replace synthetic-marker selection with a manual `0.018` map-unit `MapCursor` proximity test. Initial installer validation ran too early. |
| v0.9.5.1 | `Completionist-Map-v0.9.5.1-INSTALLER-FIX.zip` | Installer-order fix. Field result confirmed hidden-Kratos map centring, filters and marker placement, but disproved manual hover: `MapCursor:GetWorldPosition()` returned UI-root coordinates around `0,-40.222,0`, so no custom selection/compass event fired. The observed Boat Dock / ~683 m target was a stock DockPoint selection. |
| v0.9.6 | `Completionist-Map-v0.9.6-NO-MAGNET-COMPASS-FIX.zip` | Returned to v0.9.4's proven `UI.SetIsClickable()` + collision-selection path, restored marker scale `1.0`, disabled `tMapCamera` magnetic snapping completely (`CursorSnap_Enabled=0`), cleared stale stock compass destinations before custom tracking, and retained hidden-Kratos centring plus deep zoom. Initial field install aborted because the hidden-player validation again ran before its replacement. |
| v0.9.6.1 | `Completionist-Map-v0.9.6.1-INSTALLER-FIX.zip` | Stable behavioural base for v0.10.0. Installer-order-only hotfix. No gameplay/marker/compass logic changes from v0.9.6. |

## Current invariants

The ordinary test path must remain save-safe:

- no `Map.ChangeMarkerState()` on synthetic/borrowed targets;
- no synthetic `game.Compass.ShowMarker()` for arbitrary collectible XYZ;
- no artificial region-summary increments;
- no collectible/puzzle completion mutation;
- no synthetic save writes.

The custom compass target is a UI-only bearing toward stored world XYZ. Gameplay scripts are instrumented only to observe the game's own restored/completed state and to clear UI markers when the underlying object is genuinely completed.
