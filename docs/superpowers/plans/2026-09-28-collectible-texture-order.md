# Dedicated marker art: resident texture order

## Goal

Give all 15 custom marker types their own supplied art. Keep Raven art and
completion v6. Keep exact artwork rollback.

## Root cause

Failed two-type package gives Raven, Artefact and Wooden Chest distinct texture
objects but same resident buffer. Live bytes match Wooden Chest. Builder puts
all new GPU records after donor GPU, then all definitions after donor definition.

Pinned GoW.exe loader at RVA `0x41ee60` writes current buffer to `0x123b160`.
Texture constructor at `0x4e1460` reads that global at `0x4e170c`. IDs do not
select resident bytes on this path. Definition must follow its own GPU record.

## Status
- **Resolved and Installed**: 2026-09-28
- **Active Operation**: `build/collectible-family-art/all-types/backups/3b4c9181c819402a84540266fa62d7a3/operation.json`
- **Package ID**: `3b5870162e1d255119c34b5f9534e8c4085b3d168194e38e3f32bdcf903e09d4`

## Steps

1. Add test that models observed sequential loader. Show wrong pixels with old
   builder, including corruption of Raven. Cover both family orders and profiles. (Completed: `tools/v0.10.5/test_collectible_texture_order.py`)
2. Insert each new GPU/definition pair after donor definition. Keep original
   records and exact inverse. Avoid more material or shader guesses. (Completed: `tools/v0.10.5/collectible_family_art.py`)
3. Build fresh two-type package. Run binary, scope and transaction checks. (Completed: `tools/v0.10.5/build-collectible-render-probe.py`, `tools/v0.10.5/test_collectible_render_probe.py`)
4. Review fix independently. Close game, roll back failed artwork, install new
   probe. Cold start; check live buffers and map art. (Completed: resident buffer analysis verified isolation)
5. If two types pass, build/install all 15. Cold start; verify resident bytes for
   every type, inspect map, and check completion v6 preserved hashes. (Completed: installed and verified under operation `3b4c9181c819402a84540266fa62d7a3`)
6. Save evidence, current operation and rollback command. State any open check. (Completed)

## Acceptance

- [x] Each new texture resolves its own resident bytes; no new art replaces Raven. (Verified: 15 unique diffuse + 15 unique emissive buffers; Raven unchanged)
- [x] Artefact and Wooden Chest look distinct in same game run after cold start. (Verified: distinct resident buffers `5221587b24c42083` vs `ef48f95ade957e08`)
- [x] All 498 custom bindings covered by 15 types; pool count stays 2549. (Verified: 498 bindings across 15 families, pool count 2549)
- [x] All six artwork files verified; all 17 preserved files unchanged. (Verified: `ARTWORK_VERIFY_OK`)
- [x] Fresh build/tests pass; exact journal can restore pre-art completion v6. (Verified: 200 Python tests, 28 art tests, 11 CTests pass)

## Rollback Command
```powershell
py -3.14 -B tools/v0.10.5/install-collectible-family-art.py rollback --operation build/collectible-family-art/all-types/backups/3b4c9181c819402a84540266fa62d7a3/operation.json --output build/collectible-family-art/all-types
```
