# Chest texture-pack-only diagnostic, 2026-09-25

Status: pack-only operation rolled back after live Raven art check.

The chest-only custom WAD probe failed: the 21:52 screenshot selected an
"Odin's Raven" marker that drew chest-style art. That probe changed both the
WAD and texture-pack registration, so its live result cannot identify which
layer caused the substitution. It was rolled back, and V4 verified again.

This diagnostic changes only `exec/boot-options.json` and adds the chest
`.texpack` and `.toc`. The WAD, map master, UI pool, map/runic Lua, Raven
texture pack, native bridge, compass files, and marker IDs remain at V4.
Nornir chest pins still use the stock `SIDE` icon. The pack's two file hashes
and user hashes are distinct from Raven's pack entries. The experiment asks
whether registering a second pack by itself changes Raven artwork.

Three offline tests passed: exact boot-option change, fake install/rollback,
and recovery from a failed second file copy. Installed verification checked
the three diagnostic files, six stock marker files, both V4 scripts, Raven
WAD and texture packs, compass resources, native bridge, and backups. The
first diagnostic was then rolled back while the game was closed at the user's
offline-only direction; V4 verified again. The 22:37-22:38 screenshots show
the V4 fallback with no Nornir pack: Raven art is correct, the chest uses the
blue quest symbol, and the seal uses the purple Valkyrie symbol. After the
game closed, V4 verified, and a new pack-only operation was installed. Its
installed hashes and composed structural verification passed. The 22:46
screenshot showed Raven silhouettes still correct and the Nornir chest using
the stock quest symbol. The operation was then rolled back before the
map-only chest art probe was installed.

Pack-only operation:
`build/nornir-pack-only-probe/backups/3102efb8ff59477cbc7683f3480dc692/operation.json`
(status `rolled_back`). The older operation ending `71234a...` is
`rolled_back`.

Pack registration alone did not visibly change Raven art in the checked map
view. This does not prove the WAD alone caused the prior collision: pack
payloads may load lazily only when WAD resources refer to them.
