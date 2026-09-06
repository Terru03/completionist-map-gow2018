# Changelog

## v0.5-raven-registry

- Pivots from the native map-marker table to actual collectible gameplay objects.
- Adds a read-only raven diagnostic against `precisionchallenge.lua`.
- Logs each loaded raven's level/WAD, object name/ID, `regionSummaryQuest`, restored `ravenKilled` state and exact world X/Y/Z.
- Installer patches the user's own `mods/lua_source` copy at install time, avoiding bundled decompiled game source and ensuring the override matches the user's game build.
- Purpose: determine whether Midgard's raven objects instantiate realm-wide or only in currently loaded WADs.

## v0.4-diagnostic

- Correlated Midgard's native region/realm completion summaries with hidden marker records.
- Midgard result: `148 / 225` realm-summary progress.
- Tested all 244 hidden marker records against candidate collectible flags.
- Result: every hidden record returned `candidateFlags=<none>` for the tested collectible categories.
- Region-level mismatches prove missing collectible summary entries are not represented as collectible-typed native POI marker records.
- Conclusion: reject the direct hidden-marker path for collectibles and pivot to gameplay-object state/positions.
- Remained read-only: no icon creation, marker-state changes or save/progression changes.

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
