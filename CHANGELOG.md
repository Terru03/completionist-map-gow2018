# Changelog

## v0.3.1-diagnostic

- Expands detailed probing to both Midgard and Alfheim.
- Midgard is the active test realm because the current save still has missing collectibles there.
- Alfheim is used as a 100%-complete control realm.
- Logs marker state, LAMS IDs, offsets, quest association, known stock map/compass flags and scalar marker metadata.
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
