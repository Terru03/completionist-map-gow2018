# One-family Nornir map-art probe, 2026-09-25

Status: failed live art check and rolled back to checkpoint v4. Operation:
`build/nornir-one-family-art-probe/backups/3d024689091b494f986c993e529f9bb6/operation.json`.

The four-family custom WAD made Raven and Nornir child map pins draw chest art.
Separate marker IDs, model groups, prototype child IDs, and independent material
`+0x10` hashes did not stop it in live tests. This test changed one variable:
it kept only the chest's custom map art, with stock icons for seals,
bells, and mechanisms. Chest compass art stays the stock `SIDE` class for this
probe. The 21:52 screenshot selected a marker labelled "Odin's Raven" that drew
the chest-style icon. One custom chest family alone reproduces the collision.

`build/nornir-one-family-art-probe/candidate/game-root` has six files:

- `r_ui.wad`: the previous four-family WAD with the seal, bell, and mechanism
  resource groups and texture records removed. It adds one chest material and
  inverts byte-for-byte to the exact Raven WAD.
- `mapmaster.dcb`: changes the 22 Nornir chest map resources to
  `goMapIconCompletionistNornirChest`. All 53 Raven and 66 child markers stay at
  their existing IDs, positions, and map resources.
- `wad_r_ui.dcb`: replaces the 22 stock chest capacity rows with 22 custom
  chest capacity rows. The 301 existing rows and 66 child rows stay the same.
- `boot-options.json` plus chest `.texpack` and `.toc`: load only the chest
  texture pack.

The map Lua, exact checkpoint contract, `wad_r_perm.dcb`, compass graph, bridge,
and chest event scripts stay byte-identical to checkpoint v4. This is a map-art
test; its chest compass still shows the stock blue side-quest symbol.

Build and fake install/rollback test:

```powershell
py -3.14 -B tools/v0.10.5/build-nornir-one-family-art-probe.py
py -3.14 -B tools/v0.10.5/test_nornir_one_family_art_probe.py -v
```

The offline tests passed after rebasing to v4. The builder checks the WAD's exact inverse, all
22 changed chest map resources, 66 unchanged child resources, and all stock UI
pool rows. The fake game install, rollback, and injected second-file failure
restored every source file hash. The live install and installed hash verification
passed with the game closed, but the renderer check failed. The install was:

```powershell
py -3.14 -B tools/v0.10.5/install-nornir-one-family-art-probe.py install --prior-operation build/nornir-stock-saved-state-v4-test/backups/b17350f551164edc968b28cba5b7fbca/operation.json
```

After the screenshot, the game was closed and this operation was rolled back.
Checkpoint v4 again verified all installed stock and Raven hashes. The rollback
command was:

```powershell
py -3.14 -B tools/v0.10.5/install-nornir-one-family-art-probe.py rollback --operation build/nornir-one-family-art-probe/backups/3d024689091b494f986c993e529f9bb6/operation.json
```

The installer now refuses this WAD hash on future installs. The exact runtime
renderer identity causing the substitution is still unknown. The chest
texture-definition user hashes match its texture-pack entries and differ from
Raven's. The map and runic scripts were untouched by this probe and remain at v4.
