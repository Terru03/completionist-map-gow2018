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

This confirmed that hidden marker records are exposed to Lua, but later testing showed that hidden markers are not equivalent to remaining collectibles.

## v0.3.1 Midgard result

The current save is 100% in every realm except Midgard, making Midgard the active test realm and the completed realms useful controls.

Midgard exposed:

- 318 marker records
- 312 unique marker IDs
- 74 `kDiscovered`
- 244 `kUndiscovered`
- 28 regions containing marker records

The 244 hidden records are mostly infrastructure rather than collectibles. Major groups include:

- 99 `PrimaryQuest`
- 11 `PrimaryQuest,RadiusType`
- 36 `SecondaryQuest`
- 19 `SecondaryQuest,RadiusType`
- 26 `DockPoint`
- 15 `FightLocation`
- 9 `FastTravel`
- 9 records with no currently-known marker flag
- 8 `InfoOnly`

Therefore `kUndiscovered` cannot be used as a direct completionist filter.

## v0.4 strategy

Correlate the map-summary system with marker data rather than guessing from token state.

For Midgard:

1. Dump `Map.GetRealmSummary(...)`.
2. Dump every `Map.GetRegionSummaryInfo(regionId)` row, especially `CategoryStr`, `Progress`, `Goal` and `Discovered`.
3. Probe hidden markers with `Map.MarkerHasAnyFlag` for candidate collectible strings such as `Artifacts`, `LoreMarker`, `Ravens`, `RunicChest`, `LegendaryChest` and `PocketRift`.
4. If collectible flags exist, use them to isolate only relevant native records.
5. If they do not exist, pivot away from the map-marker table and enumerate collectible gameplay objects/pickups directly, then feed their positions into the map/compass UI.

The decompiled gameplay scripts already show that collectible interactions increment region-summary quests, for example `LegendaryChest`, `RunicChest`, artefact region-summary quests and lore-marker summary quests. That gives us a second path if the native marker table does not contain collectible positions.

## Safety rule

Until we understand the collectible schema, do not:

- pass `kUndiscovered` records to `Map.CreateMarkerIcon()`
- call `Map.ChangeMarkerState()` for testing
- modify collectible/save progression
