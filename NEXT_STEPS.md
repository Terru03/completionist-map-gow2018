# Next Steps

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
