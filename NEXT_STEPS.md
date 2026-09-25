# Next Steps

## 2026-09-25 current live art probe

The 22:46 pack-only test kept Raven art correct and showed the stock chest
symbol. Its operation was rolled back. The map-only chest art probe operation
`build/nornir-map-only-art-probe/backups/83d3624cdb2c446b9f20dd085d89d470/operation.json`
now has status `installed`. It changes six art/resource files above checkpoint
v4. Its live chest and Raven art result is pending. Do not treat structural
verification as a live art pass. See
`docs/research/nornir-map-only-art-probe.md`.

## 2026-09-25 saved chest attempt replay built offline

Checkpoint v5 reads the saved `completionistPuzzleAttempted` flag from the
runic chest after load and sends an exact-chest-key restore event. The map
keeps that event through the late Raven boundary. Two focused Lua 5.1 tests
pass: a saved attempt reveals children after the boundary, and a false flag
hides them on another save. The two-file candidate builds and compiles offline.
It is **not installed or checked live**. Checkpoint v4 remains the active
map/runic script layer; the map-only art probe sits above it.
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
