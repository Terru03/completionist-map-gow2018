# Separate Nornir map ID test, 2026-09-25

This first test was installed, checked in game, and rolled back. It added 22
Nornir chest IDs and 66 child IDs to native mapmaster/mapcoords. It drew them
with stock secondary quest art.
The 53 Raven marker rows and the Raven artwork WAD remain byte-for-byte intact.

Map behavior:

- Explore with `All` or `Completionist`: Raven pins and Nornir chest pins can
  appear together. Nornir child pins are hidden.
- Use a still-locked Nornir chest: its stock
  `PerformKratosInteraction_Locked()` calls the map hook. The exact level name
  and three rune references select one chest. Only its children appear.
- Break a seal: that seal pin clears. Open reward chest: its parent and children
  clear. Chest attempt state is stored as a Boolean in the runic parent's
  checkpoint table and can be republished when that actor loads.
- Nornir `Show on Compass` stays off in this placement test. Native compass
  class and custom art are a later gate.

This test has no unloaded per-chest state reader. Opened chests in unloaded WADs
may still appear. Old saves made before this test contain no attempt Boolean, so
their children stay hidden until the chest is tried again. Bell and mechanism
children stay visible after reveal until their parent chest opens.

Offline checks run on this build: 5 map/actor Lua tests, 3 installer transaction
tests, 12 static gate tests, two byte-identical builds. Installed hash verify
passed. The player confirmed separate Raven and Nornir chest pins in game, but
no children after a locked attempt. The event key lacked the `wad_` prefix in
the map lookup. Custom art and compass were absent by design in this test.

Install operation:

`build/nornir-id-test/backups/73973cad50d046109e2f350ce8500269/operation.json`

Verify from this checkout:

```powershell
py -3.14 -B tools/v0.10.5/install-nornir-map-id-test.py verify --operation build/nornir-id-test/backups/73973cad50d046109e2f350ce8500269/operation.json
```

Rollback while game is closed:

```powershell
py -3.14 -B tools/v0.10.5/install-nornir-map-id-test.py rollback --operation build/nornir-id-test/backups/73973cad50d046109e2f350ce8500269/operation.json
```
