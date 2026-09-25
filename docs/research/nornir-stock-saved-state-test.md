# Stock Nornir art with exact checkpoint state, 2026-09-25

The Raven-safe stock family build is installed. Its map and compass symbols are
existing game resources, and its 88 Nornir IDs remain separate from all 53
Raven IDs. Custom Nornir art remains unresolved: three live custom WAD builds
made Raven and child pins draw chest art and were rolled back.

The first checkpoint overlay added `NORNIR_SNAPSHOT_V1` reads to map Lua. The
native bridge returned an accepted 22-key response with 14 opened, seven
unopened, and one unknown at 15:48 local time. The 15:48:58 and 15:49:07 map
screenshots still showed the previously opened Veithurgard chest pin, while
Raven art remained correct. The Lua layer logged no `checkpoint_opened` event.
This is a failed live state check, not proof that the native checkpoint keys
were wrong. The exact request/parse timing remains under test.

The second overlay makes a bounded exact checkpoint read during map creation,
after the Raven map setup returns, then applies only state `4` as opened. It
keeps the later asynchronous poll. Invalid, unavailable, or epoch-mismatched
replies leave chest state unknown. The map log now prints
`[CompletionistMapV105Nornir] checkpoint_initial=...` with the read result.
The candidate changes only `mapmenu.lua`; Raven prefix, stock marker resources,
bridge DLL, and four untouched Raven art/compass files match prior hashes.
Lua 5.1 compilation and exact/unknown reader tests passed. A live player check
of the opened Veithurgard chest is pending.

Installed operation:

`build/nornir-stock-saved-state-v2-test/backups/9ad8d89035ab4dfdb9c24412e82ed2ea/operation.json`

The installer verified all six stock changed files, the Lua backup, bridge
hash, and four untouched Raven files. After the game is closed:

```powershell
py -3.14 -B tools/v0.10.5/install-nornir-stock-saved-state-v2-test.py verify --operation build/nornir-stock-saved-state-v2-test/backups/9ad8d89035ab4dfdb9c24412e82ed2ea/operation.json
py -3.14 -B tools/v0.10.5/install-nornir-stock-saved-state-v2-test.py rollback --operation build/nornir-stock-saved-state-v2-test/backups/9ad8d89035ab4dfdb9c24412e82ed2ea/operation.json
```

## Loaded seal state, checkpoint v3

The 18:47:45 chest screenshot shows one gray rune, but the 18:48:02 map
still shows three seal pins. At 18:46:39, `OnStart` sent a restored `seal`
event for Veithurgard. The Raven native boundary reached the map at 18:46:52;
`BeginEpoch` cleared that event. The 18:47:47 locked-chest attempt then
revealed all three children. This explains the extra broken-seal pin.

The v3 map reader checks the exact loaded parent path, calls a read-only
runic getter, and matches all three seal references. The getter returns
individual flags only if the observed broken count equals `keysUsed`.
Map creation reads these flags after the native boundary and before drawing
Nornir pins. The map retries for 180 frames if a loaded parent is late.
An unknown, mismatched, or unloaded parent has no inferred seal state.

`build/nornir-stock-saved-state-v3-test/backups/7770eff037324a53a757e5971f07b877/operation.json`
is installed. Only map and runic Lua changed over v2. The installer verified
all stock files, both backups, the Raven resources, and the bridge. The new
Lua compiled under Lua 5.1; three tests cover loaded broken flags, count
mismatch, a delayed boundary, exact seal mapping, and an in-game save switch
model. The 19:08 live log did not show `loaded_seals`, and map selection still
reached all three Veithurgard seal pins. The loaded-object path reader did
not fix this live case.

## Restored event snapshot, checkpoint v4

The runic script now sends a full three-bit seal snapshot on load and after
each broken seal. It checks the three rune refs and `keysUsed` first. The map
matches the chest event key and sorted child refs, then holds that snapshot
through the delayed Raven boundary. A newer snapshot replaces the older one
for the same chest, including flags restored as unbroken on a different save.

`build/nornir-stock-saved-state-v4-test/backups/b17350f551164edc968b28cba5b7fbca/operation.json`
is installed. Only map and runic Lua changed over v3. Lua 5.1 compile, two
mock tests, installed hashes, Raven resources, and bridge hash passed. The
user confirmed at 19:19 that broken Veithurgard seal 2 was no longer on the
map. The chest-only custom art probe was installed afterward; it leaves both
v4 scripts unchanged.

## Saved locked attempt, checkpoint v5 (offline only)

The runic script already saves `completionistPuzzleAttempted` on a locked
chest try. The v5 add-on reads that flag after `OnStart` and sends an exact-key
`restore` event. The map buffers this event through the late Raven boundary.
The event can set or clear child visibility when switching saves. Two tests
compile the candidate Lua under Lua 5.1 and check true/false replay and the
boundary. `build-nornir-stock-saved-state-v5-test.py` builds the two-file
candidate. No v5 installer exists, and v5 has no live game result.
