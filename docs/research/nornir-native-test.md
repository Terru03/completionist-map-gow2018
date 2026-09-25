# Separate Nornir native marker test, 2026-09-25

The first live ID test proved separate Raven and Nornir chest marker IDs, but its
locked chest event did not match the map lookup key. It also used stock quest art
and did not offer the compass action. That install was rolled back.

This diagnostic build was installed at `G:/SteamLibrary/steamapps/common/GodOfWar`
and rolled back after the live art test failed.
It keeps the 53 Raven rows and adds 22 Nornir chest and 66 child rows with unique
native marker IDs. Four Nornir icon families have dedicated map resources,
texture packs, and compass classes. The locked chest event lookup now uses the
observed `wad_xpl200_funeral|runiclock01|runiclock02|runiclock03` form. The
Nornir map layer handles its own selection and compass toggle and releases an
active Raven compass target before taking over.

Expected behavior:

- With `All` or `Completionist` selected, Raven and Nornir chest pins can show
  together. Child pins stay hidden while exploring.
- A locked Nornir chest attempt reveals only its linked children. A destroyed
  seal hides its own pin. Opening the reward chest hides its parent and children.
- A selected Nornir pin offers `Show on Compass` with its own icon class.

Offline proof: existing Raven WAD records and map rows are preserved; four
Nornir material runtime keys are unique; embedded texture definition names match
their new resource names; 96 UI pool rows were added without changing the 301
existing rows; the 88 mapmaster/mapcoords additions have exact inverse rebuilds.
Five ID tests, three native map tests, three native installer tests, and twelve
static gate tests passed. The full map Lua compiled under Lua 5.1. Installed
file hash verification passed after the 17-file install.

The live log confirms the native map layer loaded and the exact locked chest
attempt reached the map event receiver. The map then showed three child pins;
Nornir pins offered a compass action and the HUD showed its target. The player
also observed Raven pins taking chest artwork and seal pins drawing chest art.
This fails the artwork and Raven isolation requirements. The installed WAD and
other 16 changed files were rolled back with the operation below; a second
rollback pass confirmed all targets already matched their prior hashes.

Offline inspection found that all four Nornir map models depend on the same
`MG_mapicondock_0` model group ID as Raven. The four HUD models similarly
depend on `MG_boatdock_0`. These shared dependencies are a plausible art cache
alias, but the exact runtime cause is still unproved. Do not reinstall this
failed WAD (`ead7d42b31e08bac7fe98085b54076e008fad2a65cc88db66fc3c1b3048b60bd`).

The production static gate remains `BLOCKED_FAIL_CLOSED` because unloaded
per-chest state is not yet proved. An opened chest in an unloaded WAD may show
until that actor loads. Old saves without the attempt Boolean may need another
chest try.

The art package is pinned to a prior local candidate by manifest SHA-256
`7911b551e5a30deea0cba3f6105e76105d659664fbaaa42407e41e5a158ba640`.
The diagnostic builder needs that local package to reproduce this build.

Build and test from this checkout:

```powershell
py -3.14 -B tools/v0.10.5/build-nornir-native-test.py
py -3.14 -B tools/v0.10.5/test_nornir_native_test.py
py -3.14 -B tools/v0.10.5/test_nornir_native_installer.py
```

Install operation:

`build/nornir-native-test/backups/ebffe3cdcd3e4da393e754faa058b2e4/operation.json`

The operation has status `rolled_back`. Use the rollback command as an
idempotent prior-hash check while the game is closed:

```powershell
py -3.14 -B tools/v0.10.5/install-nornir-native-test.py rollback --operation build/nornir-native-test/backups/ebffe3cdcd3e4da393e754faa058b2e4/operation.json
```
