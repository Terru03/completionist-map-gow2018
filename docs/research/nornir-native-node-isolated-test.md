# Nornir prototype child-node isolation, 2026-09-25

**Live result: failed and rolled back.** The 14:32:48 screenshot selects a
Nornir Seal drawing chest art, and the 14:32:55 screenshot selects an Odin's
Raven drawing chest art. The child-node change did not isolate the renderer.
Operation `0e3617b4920b4a2fba5546c234e7712e` has status `rolled_back`;
the seven prior hashes match and all ten new files are absent. The candidate
WAD hash `b1ba84815a90127e9319968d18fd6a0433d1294128624a40872fa623bcaf4186`
is retired.

The model-group-only candidate failed its live artwork check. The three latest
screenshots at `C:/Users/david/Pictures/Screenshots` are
`Screenshot 2026-09-25 141214.png` (world view),
`Screenshot 2026-09-25 141238.png` (selected Odin's Raven rendered as a chest),
and `Screenshot 2026-09-25 141303.png` (selected Nornir chest with nearby child
pins all rendered as chests). The map labels and separate marker IDs still work. The failed
operation `9e240023d4fe4f5ea90b236bff041e8f` was rolled back while the game
was stopped. All seven original hashes matched and all ten new files were gone.

Read-only WAD inspection found another concrete shared identity. A map icon
prototype has a table of four internal node IDs: its root plus three children.
The Raven and all four Nornir map prototypes retained Dock's same three child
IDs. A HUD icon prototype has a root plus one child; Raven and all four Nornir
HUD prototypes retained BoatDock's same child ID. The four Nornir prototypes
had distinct outer names and IDs, but their child-node tables still collided
with one another and with Raven. The exact renderer cache behavior is an
inference; the repeated IDs themselves are directly visible in the payloads.

`nornir_prototype_child_isolation.py` gives each Nornir family three new map
child IDs and one new HUD child ID. It changes only 16 internal IDs across eight
Nornir prototypes. Raven, stock, and all other WAD records remain byte
identical. The builder reparses and reverses those 16 replacements to recover
the exact model-group-only input WAD. Eight separate model-group clones and the
existing unique materials/textures remain in the candidate.

The offline build and five tests passed, including reproducible binary output,
transaction rollback, source-drift refusal, and rejection of a missing
child-identity proof. The candidate installed while the game was closed. Its
17 installed hashes and seven Raven-base backup hashes verified. A separate
installed map parser found 53 unchanged Raven marker rows, 53 unchanged Raven
coordinate rows, and 88 new Nornir IDs with no overlap.

Installed WAD SHA-256:
`b1ba84815a90127e9319968d18fd6a0433d1294128624a40872fa623bcaf4186`.
Rollback journal:
`build/nornir-native-node-isolated-test/backups/0e3617b4920b4a2fba5546c234e7712e/operation.json`
(status `rolled_back`). The installer supports `verify` and `rollback` with this
journal.

The live artwork check failed. Unloaded per-chest state is still unresolved and
production generation remains blocked.
