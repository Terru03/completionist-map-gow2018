# v0.10.4 native Raven no-render regression

Status: **ROOT_CAUSE_PROVEN**

## Proven regression

The current v0.10.4 mixed install retained the authored Raven marker record in `mapmaster.dcb`, but lost the matching Raven identity from both:

- `mapcoords.dcb`
- `compassgraph.dcb`

The live Raven marker ID remained `E15E6BC82AE2773E`, but the current semantic parse showed:

- Raven `mapmaster` record present
- Raven `mapcoords` record absent
- Raven `compassgraph` edge absent

The historical known-good v0.10.3 native candidate contained:

- `WAD_Xpl200_Funeral`
- position `(-64.875, 12.984375, 787.5)`
- graph edge `E15E6BC82AE2773E -> BABC033C454755A0`

The failed v0.10.4 route re-proof logged `wad=nil x=0 y=0 z=0`, `ShowMarker` returning successfully, and no later native-manager verification.

Static executable tracing established that the native compass show worker performs marker membership against the coordinate registry before the CompassIconClass/resource lookup. The coordinate registry is populated from `MAP_COORDS_PERM_DATA`. A Raven ID absent from that registry can therefore pass the Lua wrapper while being rejected before HUD or in-world marker resource creation.

## Runtime A/B proof

A fail-closed A/B restored **only** the known-good `mapcoords.dcb` and `compassgraph.dcb` while preserving:

- current Raven `mapmaster.dcb`
- custom Raven map artwork
- current `wad_r_perm.dcb`
- current `r_ui.wad`
- current Raven route re-proof Lua bridge
- saves/progression/collectible state

Field result: native compass navigation and pathfinding returned for the Raven. The rendered artwork was still stock DockPoint artwork, which is expected because the route re-proof calls the native compass with `DockPoint`.

This runtime recovery promotes the conclusion from `ROOT_CAUSE_NARROWED_NOT_PROVEN` to **`ROOT_CAUSE_PROVEN`** for the no-render/native-routing regression.

## What is not the root cause

The forensic comparison also showed:

- Raven `mapmaster` non-icon fields are equivalent to the known-good marker.
- The only intentional Raven `mapmaster` change is `goMapIconDock -> goMapIconCompletionistRaven` plus its appended string.
- Current `wad_r_perm.dcb` matches the recomputed dedicated Raven CompassIconClass candidate.
- Stock CompassIconClass records, including `DockPoint`, remain byte-identical and preserve static lookup ordering/relocations.
- Current `r_ui.wad` matches the recomputed four-payload Raven HUD candidate and preserves stock resource groups/accounting.

These findings do not by themselves prove every renderer path is perfect, but the two-file runtime A/B demonstrates that missing native coordinate/graph registration was the blocker that prevented native Raven presentation.

## Next isolated test

Keep the proven native `mapcoords + compassgraph` data active and change only the Raven `ShowMarker` class from stock `DockPoint` to the already-installed `CompletionistRaven` class.

Expected result if the custom class is now fully usable:

1. native route/pathfinding remains unchanged;
2. Raven HUD artwork replaces DockPoint artwork;
3. current `CompletionistRaven.InWorld_tMPIcon_Name` still uses the DockPoint in-world resource, so an in-world Raven-specific art resource is a separate follow-up task.

Do not alter the graph, coordinates, map artwork, or saves during that class-only A/B.
