# Next Steps

## 2026-09-28 Dedicated Compass HUD Art Pipeline for All 15 Families (Completion Upgrade v12 & Full Art Package)

Dedicated Compass HUD artwork has been fully implemented across all 15 collectible families, matching the in-world 3D map icon artwork directly on Kratos's navigation compass HUD bar.

### 1. Implementation Architecture & Deliverables
1. **Engine Compass Class Registration (`wad_r_perm.dcb`)**:
   - `build_perm` appends 15 contiguous `0x20`-byte type-`0x11E` (`CompassIconClass`) export records before `COMPASS_GLOBALS` (`root = 0x4E2D08`).
   - Each record binds its respective `hud_resource` (`goCompletionist<Title>HUD`) hash as the compass icon, sets `Radius = 0`, preserves `InWorldUID = 0x0E24CF72E968ACF0` (stock side quest in-world carrier), and sets unit scale `1.0f`.
   - Data and export relocations cleanly shifted by `+15 * 0x20` (`+0x1E0`) bytes.
   - Exact-inverse byte-for-byte verification confirmed in tests and builder.
2. **UI Asset Chains (`r_ui.wad`)**:
   - `build_wad` links each family's HUD model (`MDL_cmf_<family>_hud`) to its existing family material (`MAT_cmf_<family>`) and 2D quad mesh (`MG_boatdock_0`).
   - Header type table accounting updated (`0x10001` +2, `0x20001` +2, `0x10005` +1, `0x2000C` +1, `0x10015` +2; total payloads `(typed + 3) * 15`).
   - Full exact-inverse recovery maintained.
3. **UI GameObject Pool (`wad_r_ui.dcb`)**:
   - Reassigned 15 spare stock quest pool rows (capacity 1) for the HUD Go instances (`goCompletionist<Title>HUD`), bringing reassigned pool entries to `498 + 15 = 513`.
   - Preserves capacity invariance across all 2,549 pool rows with `0` added UI physics objects.
4. **Lua Wiring & Prompt Synchronization (`collectible-location-map.lua`)**:
   - Added deterministic `familyClasses` mapping in `MapOn.ShowOnCompass` (`CompletionistArtefact`, `CompletionistCipherChest`, `CompletionistCoffin`, `CompletionistJotnarShrine`, `CompletionistLegendaryChest`, `CompletionistLoreMarker`, `CompletionistLoreScroll`, `CompletionistNornirBell`, `CompletionistNornirChest`, `CompletionistNornirMechanism`, `CompletionistNornirSeal`, `CompletionistRealmTear`, `CompletionistTreasureDig`, `CompletionistTreasureMap`, `CompletionistWoodenChest`).
   - Graceful fallback to `"SIDE"` if compass class show fails.
   - Retains strict mutual exclusion (tracking custom clears stock and native markers; tracking stock clears custom and hides pulsing rings).
   - Instant HUD prompt text updates (`CursorInfo_Top` / `CursorAction_Text` and `UpdateFooterButton`).
5. **Frozen Packages & Verified Installation**:
   - **Completion Upgrade v12**: Built in `build/collectible-completion-upgrade-v12`, installed into game under operation `5460fd4cd3d5462cac0c1241ac50588c`.
   - **15-Family Art Package**: Built in `build/collectible-family-art/all-types` (package `6fa29704cdbf35c45d0a9ef419ec26b758448af94e23ac67932f7156c35da4af`), installed into game under operation `245f4cb7675448ab89ae94f9fb677616` (`ARTWORK_VERIFY_OK`).

### Active Operations & Rollback Journals
- **Completion Upgrade v12**: `build/collectible-completion-upgrade-v12/backups/5460fd4cd3d5462cac0c1241ac50588c/operation.json`
- **Family Art with Compass HUD**: `build/collectible-family-art/all-types/backups/245f4cb7675448ab89ae94f9fb677616/operation.json`

Rollback commands:
```powershell
# Roll back family art package:
py -3.14 -B tools/v0.10.5/install-collectible-family-art.py rollback --operation build/collectible-family-art/all-types/backups/245f4cb7675448ab89ae94f9fb677616/operation.json --output build/collectible-family-art/all-types

# Roll back completion upgrade v12:
py -3.14 -B tools/v0.10.5/install-collectible-completion.py rollback --operation build/collectible-completion-upgrade-v12/backups/5460fd4cd3d5462cac0c1241ac50588c/operation.json --output build/collectible-completion-upgrade-v12
```

### Verification Summary
- **208/208** collectible tests passed (`test_collectible_*.py`).
- **64/64** raven tests passed (`test_all_ravens_*.py`).
- **3/3** dedicated compass HUD unit tests passed (`test_collectible_hud_art.py`).
- **11/11** native CTests passed (10 in `collectible-completion-bridge`, 1 in `collectible-completion-capacity`).
- Exactly 498 map bindings + 15 compass HUD classes verified with full exact-inverse byte preservation.

---

## 2026-09-28 Mutual Compass Tracking Exclusion and Raven Rapid Toggle Fix (Completion Upgrade v11)


All three user requests for map navigation and marker visibility have been implemented, tested, and installed in the game:

1. **Empty Space Click-Drag & Zoom Fix**:
   - **Prior issue**: When clicking empty space to drag the map while zoomed in, `MapOn.MouseClickHandler` in `tools/v0.10.5/collectible-location-map.lua` queried `UI.GetEventSenderGameObject()` which held a stale GameObject from prior icon clicks. This caused the camera to jump to a marker from the opposite side of the map and reset the zoom level via `Camera.PointAtGO(icon)`.
   - **Fix**: In `MapOn.MouseClickHandler`, if `not self.isOpenedForFastTravel`, we verify collision using `hasCollision = (self.mapIconCollision ~= nil or self.completionistMapV105LocationSelected ~= nil or self.currMarkerID ~= nil or self.currMarkerPlayerIcon)`. If clicked on empty space (`not hasCollision`), click handling returns immediately without moving or refocusing the camera. When an icon is legitimately clicked, `pcall(Camera.PointAtGO, icon)` was removed so the current zoom level is preserved without resetting.

2. **On-Screen Button Prompt for Show/Hide Completionist Markers**:
   - Added `MapOn.UpdateFooterButtonPrompt` hook in `collectible-location-map.lua` leveraging the existing `"ActiveMarkers"` footer button slot.
   - When viewing Filter 1 ("All") or Filter -101 ("Completionist") / custom categories, the footer bar displays `[DownButton] Hide Markers` or `[DownButton] Show Markers` (using the native Santa Monica controller glyph system, exactly matching `[SquareButton] Hide Kratos`).
   - Toggling markers via D-Pad Down (`_G.CompletionistMapV105ToggleMarkers` / `MapOn.EVT_Down_Release`) dynamically refreshes the footer prompt immediately.

3. **Persistent Show/Hide Setting Across Map Sessions**:
   - Replaced temporary local visibility flags with global persistent variables `_G.CompletionistMapV105PersistentShowAll` (default `true`) and `_G.CompletionistMapV105PersistentShowCategories` (default `true`).
   - Removed forced resets (`completionistShowAll = false`) from `MapOn.SubmenuExit` and `MapOn.Exit`.
   - The user's marker visibility choice persists across closing and reopening the in-world map and transitions between submenus.

Active operations:
- Completion Upgrade v9: operation `5e099639243441008acbdede12cc051b` in `build/collectible-completion-upgrade-v9` (`VERIFY_OK`).
- 15-Family Custom Art: operation `e988c15ba4b147a0a77b7b671ab0eb00` in `build/collectible-family-art/all-types` (`ARTWORK_VERIFY_OK`).

Verification summary:
- 11/11 native CTests pass (10 in `collectible-completion-bridge`, 1 in `collectible-completion-capacity`).
- 120/120 targeted Python tests pass across all completion, bindings, and art suites.

Rollback commands:
```powershell
# Roll back family art:
py -3.14 -B tools/v0.10.5/install-collectible-family-art.py rollback --operation build/collectible-family-art/all-types/backups/e988c15ba4b147a0a77b7b671ab0eb00/operation.json --output build/collectible-family-art/all-types

# Roll back completion v9:
py -3.14 -B tools/v0.10.5/install-collectible-completion.py rollback --operation build/collectible-completion-upgrade-v9/backups/5e099639243441008acbdede12cc051b/operation.json --output build/collectible-completion-upgrade-v9
```

## 2026-09-28 100% saved chest authority coverage (259/259 chests) installed (Completion Upgrade v8)

All 259 chests in the 410 collectible locations (99 wooden chests, 109 red coffins, 14 cipher chests, 37 legendary chests) now have persistent saved-state authority directly decoded from the active save's checkpoints by `dxgi.dll`.

1. **Chest Non-Respawn Reality in God of War (2018)**:
   - In God of War (2018), exploration and story chests (Midgard, Alfheim, Helheim, etc.) **never respawn**. Once opened, their state in the save file is permanently `OPENED` (`state == 4`).
   - The only respawning chests in the engine are the procedural maze chests in Niflheim's Ivaldi Workshop and Muspelheim repeatable trials; all 27 of those trial rewards were already excluded from the 410 locations.

2. **Resolution of the Remaining 26 Regional Chests**:
   - **Prior limitation**: In v7, exactly 233 chests were in `standard-chest-authority.json` + `legendary-chest-authority.json`. Exactly 26 chests (13 wooden chests and 13 coffins across Landsuther Mines / `xpl450`/`xpl475`, Konùnsgard / `xpl100`/`xpl150`/`xpl160`, Riverpass Chisel Dungeon / `for260`, Foothills / `foot250`, Peakspass / `peak205`, and Stonemason / `stn110`) remained unproved. When opened, they were hidden by the loaded object reader during the session, but upon restarting the game with those levels unloaded, their state reset to `unknown` and reappeared as unopened pins on the map.
   - **Fix**:
     - Derived all 26 exact native checkpoint identities (`registry_hash`, `object_hash`, `serialized_key`) from their WAD entity transform chains.
     - Verified `wooden_chest_844dbdd31fe6dc2fb08087399b65f67b` (`xpl475_huldramineslh.wad`) byte-for-byte in the user's active `game.sav` (`01ce3dc906612420bbdc2ed53cca93c5f3`, matching `[5, 4, 2, 0]`).
     - Added all 26 chests to `catalogue/standard-chest-authority.json` (increasing from 200 to 226 standard chests, bringing total chest authority to 259/259 chests = 100%).
     - Expanded `completion-bindings.json` to 304 proved saved identities (259 chests + 45 artefacts), contract hash `962f42eaf8730a3c56e14b4af6154eb0c091bd3fca6e09ab07642f230a7004c5`.
     - Recompiled native bridge companion DLL (`d0bdd5242970fafa4029cef86f6798555f9f1a995059fe4539891408f7aefea3`) and capacity shim (`18c42a84b045b672cfd82ad9cecabbd19a33380e5957f4ada6db0bfabf32b1d6`).
     - Rebuilt and installed Completion Upgrade v8 under operation `dcc735df81f848678d3373c7cce3281e`.
     - Rebuilt and installed 15-Family Custom Artwork package under operation `ac829c28d3d4428aa348f00f387ff254`.

Active operations:
- Completion Upgrade v8: operation `dcc735df81f848678d3373c7cce3281e` in `build/collectible-completion-upgrade-v8` (`VERIFY_OK`).
- 15-Family Custom Art: operation `ac829c28d3d4428aa348f00f387ff254` in `build/collectible-family-art/all-types` (`ARTWORK_VERIFY_OK`).

Verification summary:
- 11/11 native CTests pass (10 in `collectible-completion-bridge`, 1 in `collectible-completion-capacity`).
- 117/117 targeted Python completion, bindings, and art tests pass.
- All 15 dedicated marker families, 498 marker bindings, and 2,549 UI object pool rows verified.

Rollback commands:
```powershell
# Roll back family art:
py -3.14 -B tools/v0.10.5/install-collectible-family-art.py rollback --operation build/collectible-family-art/all-types/backups/ac829c28d3d4428aa348f00f387ff254/operation.json --output build/collectible-family-art/all-types

# Roll back completion v8:
py -3.14 -B tools/v0.10.5/install-collectible-completion.py rollback --operation build/collectible-completion-upgrade-v8/backups/dcc735df81f848678d3373c7cce3281e/operation.json --output build/collectible-completion-upgrade-v8
```

## 2026-09-28 marker hiding sync (Bug 1) and 278 proved chest saved identities (Bug 2) installed

Both reported issues have been fully resolved and verified in the live game installation:

1. **Marker hiding toggle clean on new saves (Bug 1)**:
   - **Root cause**: When toggling completionist markers off in Filter 1 ("All") or Filter -101 ("Completionist") via D-Pad Down (`_G.CompletionistMapV105ToggleMarkers` / `MapOn.EVT_Down_Release`), location pins hid, but Odin's Ravens and Nornir Chests ignored the `CompletionistMapV105ShowAll` / `CompletionistMapV105ShowCategories` flags and had no resync hook. On a brand-new save, exactly 2 markers remained: the Wildwoods Odin's Raven and Wildwoods Nornir Chest.
   - **Fix**:
     - Updated Raven visibility (`ravenMapVisible`, `ravenVisibilityKey`) to check `_G.CompletionistMapV105ShowAll()` in Filter 1 and `_G.CompletionistMapV105ShowCategories()` in Filters -101/-102.
     - Exposed `_G.CompletionistMapV105ResyncRavens(target)` to trigger `syncIcons(map, "toggle_markers")`.
     - Updated Nornir visibility (`visible`) to check `_G.CompletionistMapV105ShowAll()` in Filter 1 and `_G.CompletionistMapV105ShowCategories()` in category filters.
     - Exposed `_G.CompletionistMapV105ResyncNornir(target)` to trigger `sync(map)`.
     - Updated `_G.CompletionistMapV105ToggleMarkers` and `MapOn.EVT_Down_Release` to call both `_G.CompletionistMapV105ResyncRavens` and `_G.CompletionistMapV105ResyncNornir`.
     - Added `wire_toggle()` and `unwire_toggle()` to `build-collectible-completion.py` so the runtime compositions wire these hooks deterministically and reversibly.

2. **Opened chests hidden across all levels on endgame saves (Bug 2)**:
   - **Root cause**: Non-legendary chests (wooden chests, red coffins, cipher chests) defaulted to unproved bindings, which evaluated to `unknown` and remained visible unless the player loaded into their exact levels for live object observation. On an endgame save with levels unloaded, opened chests remained visible on the map.
   - **Fix**:
     - Extracted 200 proved chest identities from `identity-audit.json` into canonical `catalogue/standard-chest-authority.json` (4 legendary, 14 cipher, 96 coffin, 86 wooden chests with exact fixture states).
     - Expanded `completion-bindings.json` and `build-collectible-completion-bindings.py` to 278 proved identities (233 chests + 45 artefacts), contract hash `72d37d3cbe82eaace15cfdb35d0e5fb46897098757df8f8d2c02bbe10b91223a`.
     - Updated native bridge data generator (`generate_collectible_data.py`) to classify all 233 chests under `kCollectibleChests` (`state == 4`).
     - Rebuilt native bridge companion DLL (`59dc899bae6c1857edbf9437b76ae4f43f607cffea9e5c2e60b973841f887cd6`) and capacity shim (`38b758f503cd57612ebb685b8166e87378f698aed2d736215076835530423326`).
     - Native checkpoint decoder in `dxgi.dll` now decodes all 233 opened chests from saved checkpoints into `'collected'`, cleanly suppressing them across all levels.

Active operations:
- Completion Upgrade v7: operation `a52c3269204545d4a889791ed7348fd3` in `build/collectible-completion-upgrade-v7` (`VERIFY_OK`).
- 15-Family Custom Art: operation `79fe9812606c462eb5ae1f03b5f8449a` in `build/collectible-family-art/all-types` (`ARTWORK_VERIFY_OK`).

Verification summary:
- 11/11 native CTests pass (10 in `collectible-completion-bridge`, 1 in `collectible-completion-capacity`).
- 249 Python tests pass across all suites.
- All 15 dedicated marker families, 498 marker bindings, and 2,549 UI object pool rows verified.

Rollback commands:
```powershell
# Roll back family art:
py -3.14 -B tools/v0.10.5/install-collectible-family-art.py rollback --operation build/collectible-family-art/all-types/backups/79fe9812606c462eb5ae1f03b5f8449a/operation.json --output build/collectible-family-art/all-types

# Roll back completion v7:
py -3.14 -B tools/v0.10.5/install-collectible-completion.py rollback --operation build/collectible-completion-upgrade-v7/backups/a52c3269204545d4a889791ed7348fd3/operation.json --output build/collectible-completion-upgrade-v7
```

## 2026-09-28 clean alpha transparency pipeline and dedicated Red Chest artwork installed

Both visual issues identified in live map testing have been resolved:

1. **Dark contour and black details preserved (no stripped outlines)**:
   - **Root cause**: `tools/v0.10.5/collectible_art_textures.py` previously executed `texconv`
     with `-c 000000` (1-bit colorkey). Because source PNGs had black backgrounds,
     `texconv` set `alpha = 0` for all black and near-black pixels across the entire image.
     The game's pixel shader (`0c599dc8dc7e2170_ps_10000207.txt`) executes
     `discard_nz (alpha <= 0.0001)`, discarding all dark outlines, drop shadows, iron straps
     (e.g., Wooden Chest bands), and inner carved crevices. On snow or bright terrain, icons
     appeared washed out and bleached.
   - **Fix**: Implemented `make_clean_alpha_png()` using perimeter-seeded flood-fill to turn
     only the true external background into `alpha = 0`, keeping all interior dark details and
     the dark outer silhouette contour at `alpha = 255`. Removed `-c 000000` from `texconv`.
     Both BC7 diffuse and BC1 emissive textures now retain full contrast outlines and shading.

2. **Dedicated Red Chest artwork (replaced upright burial coffin)**:
   - **Root cause**: In the game engine data and completion bindings, the family is named
     `"coffin"` (`gocoffin_parent`, filter `-110`, label `"RED CHESTS"`, title `"Red Chest"`,
     109 placements). The initial asset was created as a literal vertical standing sarcophagus.
   - **Fix**: Replaced `assets/icons/families/coffin.png` with a dedicated horizontal Norse stone
     chest featuring heavy stone lid and pillars, intricate geometric knotwork carvings, and
     crimson red runic accents, matching the in-game Red Chests and the God of War UI style.

The complete 15-family package is built and installed under operation
`2dd57643652b47debae920d9d8b27177`, package
`4822b38058fef2f523ace81fa82f05e15ce24fab9512dd47e6f15e54570d4ac1`.

Coverage and verification:
- 15 dedicated marker families: 45 Artefacts, 14 Cipher Chests, 109 Red Chests (coffins),
  13 Jötnar Shrines, 37 Legendary Chests, 43 Lore Markers, 5 Lore Scrolls,
  24 Nornir Bells, 22 Nornir Chests, 12 Nornir Mechanisms, 30 Nornir Seals,
  21 Realm Tears, 12 Treasure Digs, 12 Treasure Maps, 99 Wooden Chests.
- All 498 custom marker bindings verified in `mapmaster.dcb`.
- UI object pool remains at exactly 2,549 rows in `wad_r_ui.dcb`.
- Verified 15 unique custom diffuse texture buffers and 15 unique custom emissive buffers.
- Raven diffuse and emissive textures verified byte-for-byte identical to baseline.
- Dark contour preservation assertion verified across all 15 families (`dark_fg > 50`).
- All 17 completion v6 preserved files verified unchanged (`ARTWORK_VERIFY_OK`).
- 200 Python collectible tests, 9 art tests with dark contour checks, 3 texture order tests, and 11 native CTests pass.

Rollback command to restore pre-art completion v6 baseline:
```powershell
py -3.14 -B tools/v0.10.5/install-collectible-family-art.py rollback --operation build/collectible-family-art/all-types/backups/2dd57643652b47debae920d9d8b27177/operation.json --output build/collectible-family-art/all-types
```

## 2026-09-27 hide-collected direct engine state upgrade installed (Digs, Maps, Shrines, Scrolls, Markers)

The completion upgrade package v2 is installed under operation
`70e1fb51f4f94eacba15a0041a413625`. It adds direct engine quest and wallet observation
for 85 non-chest collectibles:
- 12 Treasure Digs via `game.QuestManager` (`Complete` quest state)
- 12 Treasure Maps via `game.QuestManager` (parent quest activated)
- 13 Jötnar Shrines via `game.Wallets` (`HERO` and `HERO_SAVEONLY` resources)
- 5 Lore Scrolls via `game.Wallets` (`HERO` and `HERO_SAVEONLY` resources)
- 43 Lore Markers via `game.Wallets` (`HERO` and `HERO_SAVEONLY` resources)

Direct observation synchronizes on map open and poll, hiding collected/finished pins
even when their levels are unloaded. Together with the 78 native proved identities
(33 Legendary chests + 45 Artefacts), 163 collectibles now have persistent completion
coverage.

All 162 collectible tests pass, and 11 native CTests pass. Rollback of this operation
restores the chests + artefacts package `643dd4f93eb84fcbbd8d8ebf31607fa6`.

```powershell
py -3.14 -B tools/v0.10.5/install-collectible-completion.py rollback --operation build/collectible-completion-upgrade-v2/backups/70e1fb51f4f94eacba15a0041a413625/operation.json --output build/collectible-completion-upgrade-v2
```

## 2026-09-27 hide-collected upgrade installed (Chests + Artefacts)

The completion upgrade package is installed under operation
`643dd4f93eb84fcbbd8d8ebf31607fa6`. It incorporates all 45 Artefacts (`state == 3`)
alongside the 33 Legendary chests (`state == 4`), bringing saved-state authority to
78 identities. Live object observation is active for all 7 adapters across all 410 pins.

All 161 collectible tests pass, 18 package installer/proof tests pass, and 11 native
CTests pass. Rollback of this operation restores the verified Legendary package
`7d93a92c6f474c4aa72bacd95d9ff94b`.

## 2026-09-27 hide-collected runtime installed

The completion package is installed under operation
`7d93a92c6f474c4aa72bacd95d9ff94b`. Its state store, save boundaries, background
polling, compass/selection cleanup and seven loaded-object adapters are connected.
The `getfenv` startup crash and float32 timestamp timeout are fixed. Live Lua
now receives 31 collected and two remaining Legendary chests from the current
save. Map opening and category changes work with the capacity fixes retained.

160 collectible checks and 50 Raven/Nornir checks pass, plus eleven native CTests.
The current package's isolated install/verify/rollback restores all 11 target
files and preserves ten other files. Use the completion operation for rollback;
the old recovery rollback restores the pre-recovery package that crashed.

Saved-state coverage is still 33 of 410 IDs. The other 377 have loaded-object
paths, but remain visible when their exact state is unknown. Complete their
saved bindings and paired live proofs before claiming full unloaded coverage.

See [build and rollback instructions](docs/builds/v0.10.5-hide-collected.md),
[implementation status](docs/superpowers/plans/2026-09-26-hide-collected-markers.md),
and [coverage](docs/research/collectible-state-coverage.md).

## 2026-09-26 map collision pool fix verified live

The recovery retains all 410 blue quest-marker locations and eleven category
filters, plus the existing 53 Raven and 88 Nornir definitions. Startup previously
filled the engine's 732-entry marker-radius dictionary; the package needs 922
entries. The new bounded native shim supplies 2,048 entries while forwarding to
an exact copy of the original Raven/Nornir bridge. The executable is unchanged
on disk. No assertions or unrelated allocation routines are bypassed.

The later user-modified package crashed on map open with a null Dock icon. It
requested 340 Dock markers from a pool with only 40 instances. The recovery
restores the matching Raven/Nornir resources, uses blue quest icons for the
added locations, and adds 410 instances while preserving all 389 base pool rows.
All eleven replaced files are backed up, including the user's modified bridge.

The 20:38 crash dump identifies another independent limit: UI physics world 7
exhausted its 500-body pool at `GoW.exe+0x184C48` (`!m_poolId.empty()`). The new
shim sets its body and shape counts to 2,048 before the engine calculates and
allocates their backing storage. The other physics worlds are unchanged.

Thirteen location tests, six recovery tests, and the native capacity test pass.
The native test executes the generated trampoline and checks all world indices.
All eleven installed targets and four preserved-file hashes verified. Only the
DLL and ownership manifest changed from the user's 20:36 installation. Their
current enlarged icon pool and all map/category edits are preserved. The map
opened with 667 UI collision bodies and 653 query entities; the pool has 2,048
slots. All 21 filters were exercised, and another map open returned to the same
667 bodies. The user confirmed: "filters are working, map is working". Evidence
and read-only live counts are in `build/map-open-pool-crash/verification.json`.

Active recovery operation:
`build/collectible-recovery/backups/36c89608e5554c628fa5a9b5ae7695e2/operation.json`.
Both earlier location operations (`18ec8719464d459da62eec716ea17564` and
`a41b4c2bdad8482a90d22b9d303d0708`) as well as intermediate capacity operation
`5cfb3a85946b4d05b7aa479ce724bb25` are rolled back.

```powershell
py -3.14 -B tools/v0.10.5/recover-collectible-locations.py verify --operation build/collectible-recovery/backups/36c89608e5554c628fa5a9b5ae7695e2/operation.json
```

Use the recovery tool for rollback before changing older Nornir/bridge layers.
Its backups restore the user's pre-recovery package, which had map-open crashes.
Coverage and build/rollback commands are in
`docs/builds/v0.10.5-collectible-locations.md`. New locations can include already
collected items; procedural and repeatable rewards remain excluded.

## 2026-09-25 map-only art probe failed and rolled back

The 22:46 pack-only test kept Raven art correct and showed the stock chest
symbol. Its operation was rolled back. The map-only chest art probe operation
`build/nornir-map-only-art-probe/backups/83d3624cdb2c446b9f20dd085d89d470/operation.json`
now has status `rolled_back`. The live test showed Raven pins drawing chest
art again. The six art/resource files were restored; the installed files match
the Raven-safe stock Nornir checkpoint-v4 hashes. Custom artwork is deferred
at the user's request. See
`docs/research/nornir-map-only-art-probe.md`.

## 2026-09-25 saved chest attempt replay built offline

Checkpoint v5 reads the saved `completionistPuzzleAttempted` flag from the
runic chest after load and sends an exact-chest-key restore event. The map
keeps that event through the late Raven boundary. Two focused Lua 5.1 tests
pass: a saved attempt reveals children after the boundary, and a false flag
hides them on another save. The two-file candidate builds and compiles offline.
It is **not installed or checked live**. Checkpoint v4 remains the active
map/runic script layer; the map-only art probe has been rolled back.
See `docs/research/nornir-stock-saved-state-test.md`.

## 2026-09-25 current composed-package verifier added

`tools/v0.10.5/verify-nornir-composed-package.py` now compares a candidate or
sparse offline overlay with the pinned 53-Raven package. It verifies every
original WAD physical record byte-for-byte except the two accounting payloads,
all 301 original UI pool rows, Raven compass class and in-world carrier bytes,
all 53 Raven map/coordinate rows, Raven texture pack and boot options, and the
88-ID Nornir namespace. It allows Nornir additions and reports whether a WAD
already failed a live art check. It does **not** claim that byte preservation
proves runtime art isolation. The old v0.10.4 257-row runner now stops early on
the current 301/389-row package.

Read-only verification of installed V4 passed: 53 Ravens, 88 Nornir markers,
389 UI pool rows, unchanged Raven WAD and perm DCB. The four-family art package
also passed structural checks with 397 UI rows and eight separate Nornir perm
exports, but its WAD is correctly flagged as a known live art failure. The
one-family chest art probe likewise passes structural checks and is flagged
as a known live failure. Four verifier tests reject tampering of Raven WAD,
UI pool, and compass class bytes. No new custom art package was installed.

Reports: `build/nornir-composed-verifier/current-v4.json`,
`build/nornir-composed-verifier/four-family-art.json`, and
`build/nornir-composed-verifier/one-family-failed-live.json`.

## 2026-09-25 chest texture-pack-only diagnostic checked and rolled back

The failed one-family art probe was rolled back and checkpoint v4 verified.
To distinguish texture-pack registration from WAD resource cloning, a
three-file diagnostic registered only the chest texture pack. It left the
Raven WAD, all 53 Raven and 88 Nornir marker resources, map/runic Lua, bridge,
and compass classes byte-identical to v4. Three offline tests passed, including
fake install/rollback and second-file failure recovery. The first install was
rolled back before a live Raven art check. The 22:37-22:38 screenshots show
V4 stock art with no Nornir pack installed: Raven art is correct, the chest
uses the quest symbol, and the seal uses the Valkyrie symbol. After the game
closed, V4 verified and a new pack-only operation was installed. Installed
hashes and the composed structural verifier passed. The 22:46 live screenshot
showed Raven art intact and the chest still using stock `SIDE` art. The
pack-only operation was rolled back before the map-only art probe install.

Pack-only operation:
`build/nornir-pack-only-probe/backups/3102efb8ff59477cbc7683f3480dc692/operation.json`
(status `rolled_back`). The old operation ending `71234a...` is also
`rolled_back`.

## 2026-09-25 chest-only custom art failed and rolled back

The user confirmed that checkpoint v4 hid broken Veithurgard seal 2 on the
map. The chest-only custom art probe was rebased to v4 and installed while the
game was closed. It changes six art/resource files, not the map or runic Lua,
Raven marker IDs, 66 child marker resources, bridge, or compass class. The
builder proved an exact inverse from its one-family WAD to the Raven WAD and
only 22 chest map resources changed. Offline tests and installed hash
verification passed. The 21:52 screenshot selected an "Odin's Raven" marker
that drew chest-style art. The game was closed, the probe was rolled back, and
checkpoint v4 verified all installed stock and Raven hashes. The failed WAD
hash is now blocked from reinstallation. The runtime art collision is not
yet explained; stock family map and compass art is the current fallback.

Operation:
`build/nornir-one-family-art-probe/backups/3d024689091b494f986c993e529f9bb6/operation.json`.

The unfinished v5 saved-attempt replay is offline only and was not installed.
See `docs/research/nornir-one-family-art-probe.md`.

## 2026-09-25 restored seal snapshot v4 installed

The v3 live log at 19:08 still selected all three Veithurgard seals and
never logged a loaded-object read. The exact path reader did not reach live
seal state in that UI context. V4 sends a full three-bit rune snapshot from
the runic script after `OnStart` and each `OnKeyBroken`. The map matches its
exact chest key and three child refs, and carries that snapshot through the
late Raven authority boundary. This also clears a previously broken pin if
a different save restores it as unbroken. Two mock tests and Lua 5.1 compile
passed. Installed file and Raven hash checks passed. The user confirmed that
broken seal 2 disappeared from the map at 19:19; the 19:22 screenshot showed
Raven art intact.

Operation:
`build/nornir-stock-saved-state-v4-test/backups/b17350f551164edc968b28cba5b7fbca/operation.json`.

## 2026-09-25 broken-seal live read installed

The 18:47:45 chest shot shows one gray, broken rune. The 18:48:02 map shot
still shows all three seal pins. Loader log shows the game sent the broken
seal at 18:46:39, then the delayed Raven checkpoint boundary cleared Nornir
seal state at 18:46:52. The map later drew all three children after the
18:47:47 locked-chest attempt.

Checkpoint v3 now reads the exact loaded runic parent after that boundary.
The runic script returns all three rune flags only when the three references
and `keysUsed` count agree. The map matches the exact loaded placement path
and seal references, then hides broken seal pins. The reader never writes
progression. Map and runic Lua changed; Raven files, stock marker resources,
and native bridge kept their hashes. Three mock tests, Lua 5.1 compilation,
and installed hash verification passed. The 19:08 live log showed no
`loaded_seals` event and all three seal pins remained. V4 adds the restored
event snapshot above.

Operation:
`build/nornir-stock-saved-state-v3-test/backups/7770eff037324a53a757e5971f07b877/operation.json`.

The chest-only art probe above targeted v4, failed its live art check, and was
rolled back.

## 2026-09-25 chest-only custom map-art probe staged offline

The failed renderer test added only custom chest map art over the Raven-safe
checkpoint v4 build. Raven and 66 child map resources,
map Lua, bridge, and compass classes stay untouched. Its WAD inverts exactly to
the Raven base. Three offline tests passed, including fake install, rollback,
and partial-install failure recovery.
The v4 seal shot passed, but the art probe failed and was rolled back.
See `docs/research/nornir-one-family-art-probe.md`.

## 2026-09-25 map-open checkpoint read installed

The 15:48:58 and 15:49:07 screenshots show the opened Veithurgard Nornir chest
still pinned. Native bridge returned 14 opened, seven unopened, and one unknown,
but the first Lua checkpoint overlay did not apply that reply. A second,
map-Lua-only overlay now reads exact checkpoint state when the map opens and
logs `checkpoint_initial`. It is installed and hash-verified; live check awaits
player shot. Raven art and stock Nornir family icons remain untouched. See
`docs/research/nornir-stock-saved-state-test.md`.

Operation: `build/nornir-stock-saved-state-v2-test/backups/9ad8d89035ab4dfdb9c24412e82ed2ea/operation.json`.
Custom Nornir art still needs a proved renderer isolation fix.

## 2026-09-25 stock-icon Nornir compass correction installed

After the third live custom-art failure, the exact Raven baseline was restored.
A new six-file test now adds 22 Nornir chest IDs and 66 child IDs using four
existing game map icons. It does not modify `r_ui.wad`, `wad_r_perm.dcb`,
`compassgraph.dcb`, or boot options. The 14:47:55 screenshot confirms separate
Nornir map pins and restored Raven artwork. The 14:47:31 and 14:48:09 screenshots
showed that the first stock test used the boat dock flag in the compass for a
chest and seal. That operation (`004b5f3c65db47a0a23dc0fdfe225be8`) was
rolled back. Its replacement maps chest, seal, bell, and mechanism to existing
`SIDE`, `Valkyrie`, `FightLocation`, and `AreaEntrance` compass classes. This is
a stock-art visual fallback while the custom-art renderer collision remains
unresolved. The 14:57:21 chest and 14:57:42 seal screenshots confirm that
the compass and in-world markers now draw the matching blue side-quest and
purple Valkyrie symbols, with no dock flag. Bell and mechanism compass art
has not yet been checked live. See
`docs/research/nornir-stock-family-test.md`.

The current stock-icon base operation is
`build/nornir-stock-family-test/backups/998e51a12ac5461dbea27e7f07027572/operation.json`
(status `installed`). The six installed file hashes and four untouched Raven
art/compass hashes verified. Installed map and coordinate rows preserve all 53
Raven IDs and add the 88 separate Nornir IDs. Seven stock test cases pass,
including exact locked-attempt child reveal, Raven compass handoff, and fake
install rollback. Chest and seal compass art passed the live check. Custom
Nornir art and unloaded completion state remain blocked.

After the game is closed, roll back the current map-only art probe, v4, v3,
the map-open overlay, the first checkpoint overlay, then the stock base to
restore the Raven baseline. The pack-only operation is already rolled back:

```powershell
py -3.14 -B tools/v0.10.5/install-nornir-map-only-art-probe.py rollback --operation build/nornir-map-only-art-probe/backups/83d3624cdb2c446b9f20dd085d89d470/operation.json
py -3.14 -B tools/v0.10.5/install-nornir-stock-saved-state-v4-test.py rollback --operation build/nornir-stock-saved-state-v4-test/backups/b17350f551164edc968b28cba5b7fbca/operation.json
py -3.14 -B tools/v0.10.5/install-nornir-stock-saved-state-v3-test.py rollback --operation build/nornir-stock-saved-state-v3-test/backups/7770eff037324a53a757e5971f07b877/operation.json
py -3.14 -B tools/v0.10.5/install-nornir-stock-saved-state-v2-test.py rollback --operation build/nornir-stock-saved-state-v2-test/backups/9ad8d89035ab4dfdb9c24412e82ed2ea/operation.json
py -3.14 -B tools/v0.10.5/install-nornir-stock-saved-state-test.py rollback --operation build/nornir-stock-saved-state-test/backups/8ed4437f878749f697695999b189d520/operation.json
py -3.14 -B tools/v0.10.5/install-nornir-stock-family-test.py rollback --operation build/nornir-stock-family-test/backups/998e51a12ac5461dbea27e7f07027572/operation.json
```

## 2026-09-25 Nornir custom art candidate failed and rolled back

The 14:32:48 and 14:32:55 screenshots show the selected Nornir Seal and Odin's
Raven pins both drawing chest art. Distinct prototype child-node IDs did not
fix the runtime artwork sharing. The operation
`0e3617b4920b4a2fba5546c234e7712e` was rolled back while the game was
closed. All seven Raven-base file hashes match and all ten new files are absent.
The third failed WAD hash is blocked by the native installer. Do not install
another custom-art WAD until the actual shared renderer identity is proved.

## 2026-09-25 prototype child-node test history

The model-group-only candidate failed the second live artwork test. The
14:12:38 screenshot selects an Odin's Raven with chest artwork; the 14:13:03
screenshot selects a Nornir chest among child pins also drawing chest artwork.
The model-group-only operation was rolled back with all seven original file
hashes restored and all ten new files removed. See
`docs/research/nornir-native-node-isolated-test.md`.

Offline inspection found that each Nornir map prototype reused Dock/Raven's
three internal child-node IDs. Each Nornir HUD prototype reused its one internal
child-node ID. All four Nornir families therefore shared these IDs with Raven
and each other even though their outer WAD IDs and model-group IDs differed.
The new test gives those 16 Nornir child nodes distinct IDs while preserving
Raven records and the 88 Nornir marker IDs.

The new candidate was installed at `G:/SteamLibrary/steamapps/common/GodOfWar`.
All 17 installed hashes and seven Raven-base backups verified at the time, and installed
map/coordinate parsing again found all 53 Raven rows unchanged. The operation
journal is
`build/nornir-native-node-isolated-test/backups/0e3617b4920b4a2fba5546c234e7712e/operation.json`.
The live art check failed; this operation is now `rolled_back`. Production
unloaded-state generation remains blocked.

To restore the exact Raven baseline after the game is closed:

```powershell
py -3.14 -B tools/v0.10.5/install-nornir-native-node-isolated-test.py rollback --operation build/nornir-native-node-isolated-test/backups/0e3617b4920b4a2fba5546c234e7712e/operation.json
```

## 2026-09-25 model-group-only Nornir art test failed and rolled back

The eight-model-group isolation build was installed at
`G:/SteamLibrary/steamapps/common/GodOfWar` for a live artwork check. It kept
the 53 existing Raven map and coordinate rows and added 22 Nornir chest IDs plus
66 child IDs. The installer verified all 17 file hashes and its seven Raven-base
backups; a separate installed-data readback found all 53 Raven rows unchanged.
The install journal is
`build/nornir-native-isolated-test/backups/9e240023d4fe4f5ea90b236bff041e8f/operation.json`.

The live screenshot showed Raven and child artwork being replaced by chest art.
The model-group-only operation has status `rolled_back`; it must not be
reinstalled. The production unloaded-state gate remains blocked.

The rollback command was:

```powershell
py -3.14 -B tools/v0.10.5/install-nornir-native-isolated-test.py rollback --operation build/nornir-native-isolated-test/backups/9e240023d4fe4f5ea90b236bff041e8f/operation.json
```

## 2026-09-25 separate Nornir native test

The first ID test showed separate Raven and Nornir chest pins in game. It did
not show children: the chest event used `wad_xpl200_funeral` while map lookup
used `xpl200_funeral`. It also used stock quest art and hid compass action. Its
install was verified and rolled back.

The native test in `build/nornir-native-test` proved three child pins after the
exact locked chest attempt and exposed the Nornir compass action. It failed
art isolation: Raven pins acquired chest artwork and seal pins drew chest art.
The install was rolled back and prior file hashes checked. All four Nornir map
models shared `MG_mapicondock_0` with Raven; the isolated candidate above now
gives them separate groups. See `docs/research/nornir-native-test.md`.

The `BLOCKED_FAIL_CLOSED` static gate still applies to production state.
This test reads loaded chest events only. An opened chest in an unloaded WAD
may still show until its actor loads.

Nornir branch `codex/collectible-nornir-chests` starts from Raven base
`f665f61`. The isolated static gate is `BLOCKED_FAIL_CLOSED`: 22 physical
chests, 21 tracked candidates, 66 linked children, zero direct
chest-to-RegionSummary edges, and zero proved unloaded state lookups. See
`docs/research/nornir-static-gate.md`. Keep production Nornir generation off.

The Nornir marker namespace has 22 parent UIDs and 66 child UIDs, with exact
parent-child ownership and no Raven UID reuse. See
`config/collectibles/v0.10.5/nornir-marker-namespace.json`. This is not a new
God of War game/save ID. The diagnostic now registers these marker IDs in game.

The 2026-09-25 two-save Veithurgard/Mountain capture observed exact opened
checkpoint GameObject hashes for those two chests. The Mountain carrier also
matched changed save slot 3 byte-for-byte. See
`docs/research/nornir-two-save-checkpoint-evidence.md`. The two rune breaks did
not change the staged checkpoint carrier or copied save. A separately observed
live component byte tracks all six seals and the two rune breaks; its exact
`IsDestroyed()` meaning and unloaded child state remain open. Runtime generation
stays off.
The two chest hash pairs now have independent loaded GameObject identity-chain
proof, and a scoped read-only save probe confirms only the Mountain B1 opened
record. Missing records remain unknown.

Static native catalogue now has all 9 proved Ship Heads. Do not build or install
runtime markers yet.

1. Prove read-only unloaded per-object state lookup with exact catalogue keys.
   Test known complete and fresh states. Unknown or bad reply must stay hidden.
2. Find exact reason `quests.dcb` says Ship Head 10 while native data proves 9
   carriers and 9 physical objects. Do not make fake tenth row.
3. Prove exact native binding edges for any of the 21 non-Helheim Nornir
   candidates. All old 20 joins are now downgraded because source WAD identity
   plus target existence does not prove object/level-to-target ownership. Also
   prove or reject exact link from cal500 placement
   `f8548c57-4dc6-7cba-277c-5cb31099648b` to
   `RegionSummary_RunicChest_Parent_TyrsVault`. Current callback/level labels do
   not prove RegionSummary update wire.
4. Resolve the remaining 4 nontracked Legendary-path chests only from positive
   native reward, quest, callback, or story wire. The other 27 nontracked rows
   are exact arena/Surtr trial rewards and stay production-excluded. Keep all 64
   raw rows.
5. Prove stable runtime ID and world point for Niflheim procedural chest spawn.
   Do not emit 56 Legendary or 7 Nornir templates as fixed markers.
6. Prove unloaded individual state for Breakable seals. Bell and MemoryChest
   children stay tied to exact known-unopened parent.
7. Only after state gate passes, make reversible offline runtime build. Families
   stay off by default. Run static checks, two deterministic builds, rollback
   proof, then ask for game test.

Current blockers:

- Ship target mismatch: `BLOCKED_EXACT_REASON_UNKNOWN`.
- All 21 tracked-candidate Nornir bindings: `BLOCKED_EXACT_REASON_UNKNOWN`.
- cal500 Tyr's Vault binding: `BLOCKED_EXACT_REASON_UNKNOWN`.
- Legendary production eligibility: 33 tracked, 27 exact trial exclusions,
  4 unresolved (`stn200`, `xpl300`, `cal500`, `cal740`).
- Exact unloaded per-instance state: `BLOCKED`.
- Runtime generation: `BLOCKED_FAIL_CLOSED`.

Helheim extra Nornir is explained: `PASS_EXPLAINED`,
`level_scripted_untracked_triple_chest_reward`.
