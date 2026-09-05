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

## v0.2 strategy

Observe first, render later:

1. Enumerate marker records the stock map already receives.
2. Log state and IDs without changing filtering or icon creation.
3. Identify whether undiscovered collectible records are present.
4. Trace marker ID -> marker metadata / position / waypoint functions.
5. Introduce one known marker in one realm, initially Alfheim, through the safest native API discovered.
