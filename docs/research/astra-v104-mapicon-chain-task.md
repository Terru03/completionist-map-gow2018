# Astra v0.10.4 task: decode the Raven map-icon resource chain

## Time budget

Primary timebox: **90 minutes**. Hard stop: **2 hours maximum**.

At approximately 45 minutes, write the current findings to the required output file even if the investigation is incomplete. Do not consume the full 5-hour usage window trying to force a complete answer.

## Goal

Determine the smallest safe, evidence-backed offline clone recipe that can create a dedicated `goMapIconCompletionistRaven` visual resource while leaving every real boat dock unchanged.

The finished mod will continue using the proven native `DockPoint` compass/navigation type internally. This task is only about isolating the Raven **map visual resource** from stock DockPoint artwork.

## Known facts that must be treated as constraints

- The native Raven navigation architecture already works. Do not redesign it.
- `game.Compass.ShowMarker(ravenId, DockPoint)` produces the game's native compass marker, distance and path behaviour.
- A new `CompletionistRaven` `CompassIconClass` was structurally added offline but rejected by the runtime before the request queued. Do not revisit that experiment.
- The old global DockPoint texture override is retired because it turns real docks into Ravens.
- `wad_r_ui.dcb` contains a 255-entry `GOPool`; `goMapIconDock` is a 16-byte pool row, not the complete visual definition.
- Candidate Raven map icon identity:
  - name: `goMapIconCompletionistRaven`
  - hash: `584F31DC8BD6E738`
- Known Dock map textures:
  - diffuse: `982BF904AB84F2CC`
  - emissive: `FCC664130951154C`
- Do not touch or replace the native Kratos/Omega player marker artwork/material.

## Primary evidence

Start with:

- `archive/field-logs/completionist-v104-map-icon-resource-neighborhood.json`
- `archive/field-logs/completionist-v104-r-ui-prefab-inventory.json`
- `archive/field-logs/completionist-v104-r-ui-map-icon-layout.json`

Local extracted `r_ui.wad` resources are expected at:

`%LOCALAPPDATA%\CompletionistMap\work\v0.10.4\r_ui-wad-files`

The exact Dock map-icon family is contiguous:

| WAD index | Resource |
| ---: | --- |
| 13906 | `MG_mapicondock_0_gpu` |
| 13907 | `MG_mapicondock_0` |
| 13908 | `MDL_mapicondock` |
| 13909 | `ANM_mapicondock` |
| 13910 | `goProtoMapIconDock` |
| 13911 | `SCP_MapIconDock` |
| 13912 | `SWG_MapIconDock` |
| 13913 | `COL_MapIconDock` |
| 13914 | `gomapicondock` |

`goProtoMapIconDock` contains the authored-source identity:

`z:/int8/gameart/ui/general/map/mapicons.mb|NW633B8059|MapIconDock`

Use analogous stock families such as Vendor, Fight Location, Valkyrie Location, Fast Travel and Primary/Secondary Quest for structural comparison.

The `kainotoa/GOWTool` source may be inspected if useful for WAD entry/index/name handling and packing behaviour.

## Questions to answer

1. What are the binary relationships between the nine resources in a map-icon family?
2. Which fields or IDs link `MG`, `MDL`, `ANM`, `goProto`, `SCP`, `SWG`, `COL`, and the final `go...` instance together?
3. Which of the nine resources must actually be cloned for a new visual identity, and which can safely be reused from DockPoint?
4. How is the map-marker material/texture selected? The known diffuse/emissive hashes do not appear as obvious raw qwords in the nine-resource neighbourhood, so trace the real linkage rather than assuming direct hash storage.
5. What WAD resource-table metadata, names, hashes, indices or references must change to add the Raven clone without replacing a stock entry?
6. Can `wad_r_ui.dcb` then add a corresponding `GOPool` row for `goMapIconCompletionistRaven`, and what exact pool value/reference should its second qword contain?
7. Produce a concrete offline-only build algorithm that can be implemented and reparsed before any runtime test.

## Safety / non-goals

Do **not**:

- modify the installed game;
- make a runtime `ShowMarker` experiment;
- mutate save/progression state;
- restore the global DockPoint Raven texture override;
- create or retry a custom `CompassIconClass`;
- replace the Kratos/Omega player marker;
- redesign native compass/pathfinding;
- expand to all Ravens yet.

This is static reverse engineering and a clone-plan task only.

## Required output

Write findings to:

`docs/research/astra-v104-mapicon-chain.md`

The file must exist before the timebox expires, even when the result is partial.

Use this structure:

1. **Status:** `PASS`, `PARTIAL`, or `BLOCKED`
2. **Executive conclusion**
3. **Nine-resource family map**
4. **Cross-family evidence** with exact offsets/fields/values where discovered
5. **Material/texture linkage**
6. **Minimum clone set**
7. **Required WAD/DCB edits**
8. **Offline build algorithm**
9. **Unresolved unknowns**
10. **Next smallest experiment**

If blocked, document the blocker precisely and stop. A durable partial result is preferable to exhausting the entire usage allowance.
