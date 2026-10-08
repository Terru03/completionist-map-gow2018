# v1.0.4 opened-chest feedback and test fix

The player reports v1.0.4. Supplied photos show an opened red/coffin chest and
an opened wooden chest with collectible markers still present. The selected
red-chest map pin says **Not collected**. That caption means the location store
contains `remaining`; `unknown` would instead show `Collectible location`.
The exact catalogue IDs and the player's logs have not been supplied, so the
cause of these particular screenshots remains unconfirmed.

## Reproduced defect

The loaded reader accepts a unique physical placement when its outer scene
ancestors are collapsed at runtime. It subsequently requires the owner's full
archived path, including those same absent outer ancestors. Consequently an
exact owner inside the accepted placement is rejected before its opened state
can be read. A previously accepted `remaining` state persists and its pin stays.

The new regression reproduces this failure in the original released v1.0.4 Lua,
without changing game/save data or relying on the author's completion history.

The fix validates every expected owner node between the script owner and the
accepted placement, then checks that the final ancestor is that exact placement
object. It allows collapsed ancestors outside the placement while retaining
checks for duplicate placements, duplicate owners, wrong inner paths, owners
outside the placement and save changes during a read.

## Validation

- New regression fails before the fix: opened chest stays `remaining`.
- 21 source loaded-reader tests pass after the fix, including restoring the
  same chest to `remaining` when an older save is loaded.
- 31 completion/map integration tests pass, including hiding collected pins,
  clearing compass targets and keeping other uncollected pins.
- 15 chest/ownership tests pass against Lua extracted from the candidate ZIP
  under Lua 5.2. The failing case is separately reproduced against the original
  ZIP's Lua 5.2 code.
- The full candidate map Lua compiles under Lua 5.2.
- All 20 installed payload hashes and sizes match the candidate manifest.
  Only `mapmenu.lua` changes among installed payloads. The native DLLs and all
  four installer files match v1.0.4 byte for byte. The original release ZIP is
  unchanged.

These are offline tests. They do not prove the reporting player's actual
hierarchy or resolve every saved-state/collection case.

## Candidate package

File: `startup-support/CompletionistMap-v1.0.4-chest-tracking-test.zip`
relative to this worktree's parent directory.

SHA-256: `0c62c03661e47e8934586bdd9e2fd5f4dd6816be6ebfa2da13f1d832b87f3117`

Built by the task-owned ignored helper
`build/chest-feedback-20261006/verify_and_package.py` from the unchanged
v1.0.4 release ZIP, SHA-256
`f0bdf156ff13757f97d35573ae508c7c80f4bf357d81591b7708a499fc35e59d`.
The test package was sent to klibaski on Discord on 2026-10-06, with its SHA-256
and size checked before attaching it once. The [posted reply](https://discord.com/channels/1556343296023068812/1556343301081403514/1557099652963110982)
was read back after the upload completed.

On 2026-10-08 the author reported that the tester's feedback was successful.
The follow-up visible in the Windows-Test Discord session confirms opened red
and common chest markers disappear and killed Ravens are tracked correctly.
This is field evidence for that player's case; it does not establish every save
or collectible case. The production v1.0.4 package preserves all 20 installed
payloads and all four installer files from this tested ZIP, changing only release
metadata and documentation. See the [release record](../releases/v1.0.4-release.md).

Close the game, extract the full candidate ZIP and run `Install.bat`. Keep the
existing `completionist_backup` directory. Test the reported opened chests
nearby after five seconds, reopening the map, a newly opened chest, checkpoint
reload and an older save where the chest is unopened. If the failure persists,
obtain `loader_log.txt` and
`mods/completionist-map/native/raven-native-bridge.log` immediately after the
reproduction, together with the selected pin's location.

Native saved-state delivery also currently depends on accepted Raven authority.
An ambiguous Raven snapshot can delay native chest/artefact reads, although
loaded-object observations can run independently. This separate possible
failure was inspected but has not been changed; it is not established as the
cause of the photographed chests.
