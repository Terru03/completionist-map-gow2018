# Changelog

## v0.2-diagnostic

- Removed all attempts to create icons for undiscovered markers.
- Added diagnostic logging around `Map.GetMarkersInfoTable(regionId)`.
- Logs realm, region, marker ID and marker state.
- Does not modify collectible progress or save data.

## v0.1-test

- First prototype attempting to expose hidden/undiscovered map markers.
- Opening the map caused a game crash.
- Likely failure points include passing `kUndiscovered` records into `Map.CreateMarkerIcon()` and treating completion categories as marker flags.
- Removed from the user's installation immediately after testing.
