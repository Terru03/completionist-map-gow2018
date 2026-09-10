# Raven Twin Stage A2: serialized-type accounting correction

## Decision

Raven Twin Stage A failed at runtime in transaction `20260910T074936Z-7bcd87c7`.
The map rendered briefly, stock Dock markers displayed Raven artwork, and the game
then crashed. Normal rollback restored the frozen production Raven state.

The Stage A builder contains a concrete bookkeeping regression that matches a
historical defect already corrected before the first custom Raven map class
succeeded at runtime.

This finding does **not** prove that the bookkeeping defect is the only runtime
cause. Stage A2 is a one-variable runtime probe after offline validation.

## Concrete defect

`build-raven-twin-stage-a-offline.py::accounting_update()` assigns each cloned
payload to a WAD type row by testing whether the clone donor's **physical payload
index** lies inside the row's `base..base+count` range.

That interpretation is known to be wrong. WAD type-table rows are keyed by the
serialized resource type signature, not by physical payload index ranges.

The failed Stage A proof records the resulting incorrect accounting:

- source typed total: `16805`
- candidate typed total: `16813`
- accounted delta: `8`
- increments:
  - `0x20001 += 4`
  - `0x2000C += 3`
  - `0xD += 1`

The Raven Twin has eight new physical data-bearing payloads, but only six belong
to the relevant WAD typed cohorts. The two GPU texture payloads are physical
payloads and are not members of these type-table rows.

The corrected deltas, already established by the first corrected Raven custom
map-class builder, are:

- `0x0000000A += 1` — material
- `0x00010001 += 1` — prototype
- `0x00020001 += 1` — final/root instance
- `0x0002000C += 1` — model
- `0x00010015 += 2` — diffuse/emissive texture definitions

Total typed delta: **6**, not 8.

Therefore a correct Stage A2 candidate must change the source typed total from
`16805` to `16811` while still adding eight physical payloads.

## Stage A2 implementation

`tools/v0.10.4/build-raven-twin-stage-a2-offline.py` imports the existing Stage A
builder and replaces only `accounting_update()`.

All other Stage A construction remains unchanged:

- same Raven Twin marker identity and position
- same Raven Twin root/prototype/model/material/texture identities
- same Raven artwork
- same opaque donor bytes
- same `wad_r_ui.dcb`
- same `mapmaster.dcb`
- same `mapcoords.dcb`
- same map-only scope
- no compass/in-world work
- no lifecycle logic
- no Nornir artwork

The correction classifies each cloned payload using its serialized type
signature (`kind`, `flags`, first payload dword/normalized type word). Unknown
payload shapes fail closed. The two GPU texture records are explicitly recognized
as the only untyped physical payloads in this probe.

## Acceptance gate

Before any runtime install, build Stage A2 offline and require:

1. physical payload delta = 8
2. typed payload delta = 6
3. untyped GPU payload delta = 2
4. exact type increments listed above
5. final typed total = 16811
6. exact inverse normalization to frozen Raven remains true
7. Raven/stock Dock/BoatDock preservation proofs remain true
8. `wad_r_ui.dcb`, `mapmaster.dcb`, and `mapcoords.dcb` hashes remain identical to failed Stage A; only `r_ui.wad` changes
9. no game writes and no game launch

Only after those checks pass should a new transactional Stage A2 installer be
created with newly pinned candidate hashes. Do not reuse the failed Stage A
installer hashes.

## Runtime question

The Stage A2 human test asks only:

> Does the map remain stable with the original Raven and Raven Twin after fixing
> WAD serialized-type accounting, while stock Dock markers remain stock?

A success would establish the reusable second-class path. A failure means the
known bookkeeping bug was real but not sufficient, and the next probe should be
a canonical multi-class WAD reconstruction from the original stock WAD rather
than another opaque-field mutation.
