# Research notes

## Map pipeline findings

The decompiled map UI indicates that the native map obtains marker records through:

```lua
Map.GetMarkersInfoTable(regionId)
```

The stock UI recognises marker/token states including:

- `tweaks.eTokenState.kDiscovered`
- `tweaks.eTokenState.kDiscoveredButLocked`
- `tweaks.eTokenState.kUndiscovered`

The stock map's rendering path creates icons with a call resembling:

```lua
Map.CreateMarkerIcon(markerId, regionId, "")
```

The completion/region summary data also contains categories corresponding to collectible classes such as artefacts, lore markers, ravens, runic chests and legendary chests.

## v0.1 lesson

Do not assume an undiscovered marker record is accepted by the same icon construction path as a discovered marker. The crash strongly suggests the hidden state is intentionally filtered before icon creation, or that additional discovery-time state/data is required.

## v0.2 result

The read-only diagnostic succeeded on the user's current save.

For Alfheim, `Map.GetMarkersInfoTable(regionId)` returned:

- 27 marker records in total
- 23 `kUndiscovered`
- 4 `kDiscovered`
- 26 unique marker IDs

At least one marker ID appears in more than one region. Midgard and Helheim also returned substantial numbers of `kUndiscovered` marker records.

This confirms that hidden marker records are already exposed to Lua. The project should prefer resolving those native records rather than maintaining a separate hand-authored coordinate database.

## v0.3 strategy

Keep the probe read-only and restrict detailed logging to Alfheim. For each marker, collect:

1. ID and token state.
2. `LamsNameId` / `LamsDescriptionId`.
3. `OffsetX` / `OffsetY`.
4. Quest association from `questUtil.FindQuestForMarker`.
5. Known stock map/compass flags.
6. Scalar fields exposed directly by the marker info table.
7. Scalar fields returned by `Map.GetMarkerInfo(id)`.

The aim is to find a stable discriminator for collectible-like hidden markers and identify any position/waypoint-relevant metadata before attempting rendering again.

## Safety rule

Until we understand the hidden marker schema, do not:

- pass `kUndiscovered` records to `Map.CreateMarkerIcon()`
- call `Map.ChangeMarkerState()` for testing
- modify collectible/save progression
