# Nornir map-only chest art, 2026-09-25

Status: installed for live art check; live artwork isolation remains unproved.

The 22:46:27 screenshot shows the selected Nornir chest as a blue quest icon
and visible Raven pins retaining their Raven silhouettes. The installed files
match the pack-only diagnostic: original Raven WAD plus chest texture pack
registration. Registering the pack did not visibly replace the Raven art in
this view. The custom chest textures are not referenced by this WAD, so lazy
texture loading remains a possible part of the collision.

Inspection found that the previous chest-only map-art experiment still added
three Nornir HUD groups containing a model, prototype, instance and local
script, even though its compass class and HUD pool remained stock. The new
candidate removes these unused HUD additions. It retains only the custom
chest map material, model, prototype, instance and diffuse/emissive texture
definition/resident pairs: eight physical payloads and six typed resources.
This tests whether the extra HUD resources contribute to the collision; it
does not establish that they caused it.

Candidate WAD SHA-256:
`539ca1823fe5deca64349772ec9f26d4e7b73af1e0a077b852dbb1dcec549caa`.

Removing the new map resources and restoring the two accounting payloads
recovers the proven Raven WAD byte-for-byte. The composed verifier preserves
all 53 Raven and 88 Nornir markers, the original 301 UI pool rows, Raven art,
compass class and carrier. Only the 22 chest map bindings target the new art;
the children and compass retain their stock fallback symbols.

Five checks passed: artifact reproduction, rejection of the old HUD-bearing
candidate, fake install/rollback, failed-copy rollback, and refusing pack
rollback while the game is running. Installation reuses the tested six-file
transaction. Its optional pack-operation argument restored V4 before adding
the new map-art probe. The pack-only operation is now `rolled_back`; the
map-only art operation
`build/nornir-map-only-art-probe/backups/83d3624cdb2c446b9f20dd085d89d470/operation.json`
has status `installed`. Live chest and Raven art checks are pending.

Install command used after God of War closed, from the repository root:

```powershell
py -3.14 -B tools/v0.10.5/install-nornir-map-only-art-probe.py install --prior-operation build/nornir-stock-saved-state-v4-test/backups/b17350f551164edc968b28cba5b7fbca/operation.json --pack-operation build/nornir-pack-only-probe/backups/3102efb8ff59477cbc7683f3480dc692/operation.json
```

The live check must show the custom chest map icon and nearby Raven icon
together. The selected chest must be labelled Nornir Chest, and selecting the
Raven must still show Raven art. Do not infer restart/save persistence from
this art test.
