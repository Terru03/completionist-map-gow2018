# Changelog

## v0.5.1-raven-registry-diagnostic

- Fixes the v0.5 installer assumption that `mods/lua_source` contains `precisionchallenge.lua`.
- Searches local loader source/override paths first.
- If absent, downloads a pinned `MorseTheCode/GoWLUA` copy from commit `1958cf514d56e1278f02570c876ad127462b3551`.
- Validates raven-script structural signatures before patching.
- Instruments only `precisionchallenge.lua::OnStart` to log raven object identity, region-summary quest, restored completion state and world coordinates.
- Remains read-only with respect to collectible, quest and map progression.

## v0.5-raven-registry-diagnostic

- First gameplay-object registry probe, focused on Odin's Ravens.
- Intended to instrument `precisionchallenge.lua` and determine whether raven objects are instantiated realm-wide or only for loaded WADs.
- Initial installer failed safely because the user's `mods/lua_source` set does not contain that gameplay script. No override was written.

## v0.4-diagnostic

- Correlates Midgard's native region/realm completion summaries with hidden marker records.
- Dumps `Map.GetRegionSummaryInfo(regionId)` and `Map.GetRealmSummary(...)` scalar fields.
- Safely probes candidate collectible marker flags including artefacts, lore, ravens, runic/Nornir chests, legendary chests and pocket rifts.
- Logs hidden marker IDs with known infrastructure flags and any candidate collectible flags.
- Remains read-only: no icon creation, marker-state changes or save/progression changes.

## v0.3.1-diagnostic

- Expands detailed probing to both Midgard and Alfheim.
- Midgard is the active test realm because the current save still has missing collectibles there.
- Alfheim is used as a 100%-complete control realm.
- Logs marker state, LAMS IDs, offsets, quest association, known stock map/compass flags and scalar marker metadata.
- Midgard result: 318 marker records, 312 unique IDs, 74 discovered and 244 undiscovered. Hidden records are dominated by quest, dock, fight and travel infrastructure, proving `kUndiscovered` is not a collectible filter.
- Remains read-only: no icon creation, no marker-state changes and no save/progression changes.

## v0.3-diagnostic

- Restricts detailed probing to Alfheim to keep logs manageable.
- Logs marker state, LAMS IDs, offsets, quest association and known stock map/compass flags.
- Dumps scalar fields exposed by the marker info table and by `Map.GetMarkerInfo(id)`.
- Remains read-only: no icon creation, no marker-state changes and no save/progression changes.

## v0.2-diagnostic

- Removed all attempts to create icons for undiscovered markers.
- Added diagnostic logging around `Map.GetMarkersInfoTable(regionId)`.
- Logs realm, region, marker ID and marker state.
- Confirmed on the user's save that Alfheim exposes 27 records, including 23 `kUndiscovered` records and 4 `kDiscovered` records.
- Does not modify collectible progress or save data.

## v0.1-test

- First prototype attempting to expose hidden/undiscovered map markers.
- Opening the map caused a game crash.
- Likely failure points include passing `kUndiscovered` records into `Map.CreateMarkerIcon()` and treating completion categories as marker flags.
- Removed from the user's installation immediately after testing.
