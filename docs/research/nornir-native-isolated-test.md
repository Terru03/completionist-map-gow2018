# Isolated Nornir model group test, 2026-09-25

**Live result: failed and rolled back.** Raven and Nornir child pins still drew
chest artwork. The model-group-only operation
`9e240023d4fe4f5ea90b236bff041e8f` has status `rolled_back`, and the
original Raven hashes were restored. See
`nornir-native-node-isolated-test.md` for the newly installed child-node test.

This is the next live candidate after the native test's artwork failure. The
prior test established separate native IDs for 22 chests and 66 children, a
locked-attempt child reveal, and a working Nornir compass prompt, but Raven
pins acquired chest art and seals also drew chest art. The failed install was
rolled back before this build.

The new WAD clones the original map and HUD model groups for each of four
Nornir families. Each of the eight clones has a new resource name and ID;
Nornir models link to their own clone. Raven models keep their original model
group links. The offline builder reparses the WAD, checks unique references and
type accounting, and reverses the eight additions to recover the exact input
art WAD. This isolates a plausible cache key, but the runtime cause of the
earlier artwork alias remains unproved until the live check.

Build and checks used Windows Python 3.14:

```powershell
py -3.14 -B tools/v0.10.5/test_nornir_native_isolated_test.py -v
py -3.14 -B tools/v0.10.5/build-nornir-native-isolated-test.py
py -3.14 -B tools/v0.10.5/test_nornir_native_test.py -v
py -3.14 -B tools/v0.10.5/test_nornir_map_id_test.py -v
```

All four isolated tests, three native tests, and five ID tests passed. The
game process was closed before installation. The installer verified all 17
installed hashes and all seven backed-up source hashes. An independent parser
readback found 53 unchanged Raven marker rows and 53 unchanged Raven coordinate
rows, alongside the 88 new Nornir IDs with no collision. Installed WAD SHA-256
is `60c95709e027637e749a460c64a5cc04a661eca6f4da8a3bef36640ffbeb7130`;
the Raven-base WAD backup is
`5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60`.

Historical install journal:
`build/nornir-native-isolated-test/backups/9e240023d4fe4f5ea90b236bff041e8f/operation.json`
(status `rolled_back`). The `verify` and `rollback` actions in
`tools/v0.10.5/install-nornir-native-isolated-test.py` use this journal.

The live check showed chest artwork on a selected Odin's Raven and on Nornir
child pins. This invalidates the model-group-only isolation claim. Production
generation stays blocked pending artwork and unloaded-state proof.
