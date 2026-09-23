# One Legendary Chest map and compass test

This pack is for branch `codex/collectible-legendary-chests` only. It does not start God of War. It does not write chest, quest, save, or progression state. No chest-open logger exists in this pack.

## Target and state

- Catalogue ID: `legendary_chest_529343984fc313504ac20da874d05c01`
- Physical GUID: `52934398-4fc3-1350-4ac2-0da874d05c01`
- WAD: `xpl920_islandclimb.wad`
- Physical world XYZ: `(237.04469289824766, 0.9680004119873047, -30.207650585440433)`
- Persisted serialized key: `01ef10efa930c0f345ff1b9925dd64a8fe`
- Frozen raw value: `010000803f`, a tagged little-endian float32 `1.0`.
- Pristine `interact_chest_standard.lua` SHA256: `943021f321c708561e62d4c9b6926c01b3c131c2057fbed7e4c136dbed707bdc`. Its `states.ENABLED` is `1` and `states.OPENED` is `4`; its open handler sets `state = states.OPENED`. Frozen sample is thus `ENABLED`, not `OPENED`. It is a historical observation, so the player still must check the chest in game.

## Raven delivery reused

The archived Raven release candidate comes from `codex/all-ravens-release-candidate` commit `e522268e45bdd0d8f966bdb7ddf336eb344cad7d`, with every source file checked against its release proof. Installed Steam build 11168363 has 382 stock map markers and 405 stock coordinates, no Raven donor marker, and no Raven icon pool. This pack first replaces the five pinned stock/custom map files with the proven Raven release contents, then adds one diagnostic native marker, coordinate, and icon pool row. The read-only builder proves all 382 stock markers and 405 stock coordinates survive and the Raven delta remains 53. Old custom map file bytes get backed up before replacement.

The map code uses Raven's `game.Map.GetMarkerInfo`, `Map.FindRegionFromMarker`, and `Map.CreateMarkerIcon`. Selection uses the Raven exact collision object and `GetShowOnCompassPrompt`. Pressing Add to Compass uses Raven's `MapOn.ShowOnCompass` and `game.Compass.ShowMarker(selected.Name, "CompletionistRaven")`. The native Raven authority bridge `dxgi.dll` and its build manifest are bundled and hash checked, then installed with the existing bridge installer. Raven `precisionchallenge.lua` is byte-for-byte the proven release file. The diagnostic row stays outside the 53-Raven progression authority table and is forced visible. Neither map opening nor install auto-selects a route.

Native `mapcoords.dcb` stores float16 coordinates. The delivered map XYZ is `(237.0, 0.9677734375, -30.203125)`, at most `0.0447` world units from the proven physical point. This is the exact representation of that point in the Raven format, not a coordinate-based identity inference.

## Prepare, evidence, restore

`tools/v0.10.5/run-legendary-live-test-marker.ps1` has no parameters. It creates an external transcript before Git checks, safely pulls this branch, invokes the installer, and archives success or failure under `archive/field-logs/runtime-captures/legendary-live-test-marker-prepare-*`. It commits and pushes that evidence where branch and Git state allow. External evidence stays under `%LOCALAPPDATA%/CompletionistMap/legendary-live-test/` if Git archival fails.

The inner installer rejects any unpinned game executable, `mapmaster.dcb`, `mapcoords.dcb`, `wad_r_ui.dcb`, map Lua, event Lua, chest script, existing bridge, dirty tree, wrong branch, or running game. It backs up all five replaced files, verifies post-write hashes through the proven Raven transaction engine, and auto-restores on install failure. The Raven bridge installer keeps its own recovery journal. The evidence stores both before and after hashes, backup files, transaction manifest, delivered map point, target identity and state proof, terminal transcript, install result, bridge manifest, `mods/loader_log.txt` starting size/hash, and restore path. For manual runtime observation, inspect `mods/loader_log.txt` entries with `LEGENDARY_LIVE_TEST_MAP_PIN` and `LEGENDARY_LIVE_TEST_COMPASS` after game play.

After the test, with God of War closed, `tools/v0.10.5/restore-legendary-live-test-marker.ps1` validates and restores the five map files, then rolls back the Raven bridge. If a failure says not to launch the game, inspect transaction and external transcript first.

Offline proof: `candidate-offline-proof.json`. This proves candidate construction, not live map visibility, selection, compass guidance, or chest presence. Those are the manual gate.
