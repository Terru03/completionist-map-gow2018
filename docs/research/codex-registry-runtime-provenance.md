# GoW registry runtime provenance

## Result

`BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY` remains correct.

Static analysis now proves who creates, populates, reuses, resets, and destroys the 64-entry GameObject registry table. It also proves that canonical no-hint allocation is driven by runtime scheduler state, not by the physical WAD record index exposed in the catalogue. The same `(registry_id, slot)` tuple is not yet reconstructible offline for a canonical catalogue instance.

`BLOCKED_EXACT_UNLOADED_STATE_ORACLE` also remains correct. This work does not bind a Raven's `ravenKilled` field to restored per-instance save state.

All RVAs below are for `GoW.exe` SHA256 `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`.

## Runtime table owner

The table is `0x22A98C0..0x22A9AC0` (64 qword entries). The old linear executable-section scan found only unrelated direct writes near the table. Function-bound disassembly plus register taint finds the two computed table writes:

- `0x4F37A2`: `mov qword ptr [r14 + rax*8], rdi` inserts a new registry into the first null table entry.
- `0x4F35A5`: `mov qword ptr [r9 + rax*8], rdx` removes the matching entry; `rdx` is zero on this path.

Creation starts at `0x4F3660`. It reads WAD `+0xC3C` at `0x4F366B`, scans all 64 table entries, and compares registry object `+0x00` with that ID at `0x4F368A`. A match is reused. A miss falls through the adjacent pdata chunk at `0x4F36A2`, allocates a `0x38`-byte registry, and publishes it at `0x4F37A2`. Calls at `0x4B5329` and `0x4B6018` invoke this path during WAD setup/load.

Teardown starts at `0x4F3520`. It reads the same WAD ID at `0x4F3534` and finds the matching registry. Calls at `0x4B52B0` and `0x4B64F1` invoke it from WAD detach/teardown paths.

## Registry fields and reset scope

The constructor zeroes the registry before use:

| Field | Initial value | Exact evidence |
|---|---:|---|
| `+0x20` slot-bank pointer | zero, then a zero-filled `0x2000`-byte allocation | `0x4F3719`, allocation at `0x4F3749`, store at `0x4F375C`, clear at `0x4F3769` |
| `+0x28` circular cursor | `0` | qword zero at `0x4F371D` |
| `+0x2C` live count | `0` | same qword zero at `0x4F371D` |
| `+0x30` capacity | `0x400` (1024 qword slots) | `0x4F3773` |

The table and bank are therefore fresh on registry creation. Existing registries are reused by ID without constructor reset.

The teardown function has two distinct branches:

- Soft branch: WAD `+0xC38` bit test at `0x4F356B..0x4F3577`, then `0x4F3579` clears registry `+0x10` and `0x4F357C` clears cursor `+0x28`. It does **not** clear the `+0x20` bank or `+0x2C` live count.
- Full branch: `0x4F35A5` clears the table entry; `0x4F35DD` onward frees the `+0x20` bank and then the registry.

Thus cursor reset is proved at creation and on the flagged soft teardown branch. It is not valid to say every stream-in or reload clears the bank and cursor together. A same-ID stream-in can reuse existing registry state.

## Registry ID

`0x82CF00` owns a runtime metadata-record array with `0xA8`-byte records.

- Existing record path: `0x82D1A9` loads record `+0x24`; `0x82D203` stores it to WAD `+0xC3C`.
- New record path: `0x82D245..0x82D251` appends record index `edi`; `0x82D300..0x82D31B` divides byte offset `index * 0xA8` back by `0xA8`; `0x82D31E` adds `0x12`; `0x82D321` stores `record_index + 0x12` to record `+0x24`. `0x82D3B2..0x82D3B7` then copies it to WAD `+0xC3C`.
- `0x82D219` and `0x82D34F` store the current runtime context ordinal to record `+0x28`. This field is bookkeeping separate from registry ID and separate from registry cursor `+0x28`; it does not select the global table entry.

Registry ID is deterministic for a fixed metadata-record input order. The catalogue does not currently expose that metadata-record ordinal, so it cannot yet calculate the Raven WAD's exact `registry_id`.

## Canonical allocation order

The canonical object path remains no-hint:

- `0x859BA9` writes `0xFFFFFFFF` as descriptor slot hint.
- `0x859BD6` calls `0x8566B0`.
- `0x859C0D` calls `0x856F50`, which reaches the no-hint allocator.

But the calls are not a direct walk over physical WAD records. `0x85AC27` is a time-budgeted runtime scheduler:

- `0x85AC80` walks an outer runtime list.
- `0x85ACD5` walks each node's inner list.
- `0x85AEC1..0x85AEEC` processes a bounded number of items and calls `0x858320` at `0x85AEE3`.
- `0x8583E2..0x85840F` resolves the passed outer and inner list indices.
- `0x85847E..0x8584E0` advances global LCG state and selects a runtime variant before the later builder/loader calls.

The allocator slot is therefore a function of the registry's live/free bank and cursor at the exact scheduler call, including earlier allocations and frees. Physical WAD order is useful evidence, but no static edge proves it equals this runtime allocation ordinal.

## Concrete Raven

For catalogue instance `95b9c644-4d47-9ac6-8207-b1829d02909b` in `alf355_chiseldungeon.wad`:

- catalogue final record ID: `44c6b995c69a474d82b107829c90029d`
- catalogue final offset: `0x32E3C60`
- strict WAD parse: 26,898 physical records
- exact canonical final record: zero-based physical record index `9633`, kind `1`, flags `0x3D`, size `164`

The same ID also appears later in a zero-size record, so ID alone is not enough; the catalogue's offset selects the canonical instance record. There is no proved conversion from physical index `9633` to scheduler indices, prior allocator cursor/bank state, or slot. No `(registry_id, slot)` value is claimed.

## Single missing edge

The narrow missing edge is:

```text
canonical catalogue/WAD record
  -> exact runtime allocator-entry state at its scheduler call
     (registry ID, cursor, live/free bank, and allocation ordinal)
  -> same state after reload
```

A narrow read-only runtime trace should log `WAD +0xC3C`, scheduler outer/inner indices, allocator entry cursor, selected slot, and the catalogue record ID/offset on two clean reloads. Only an identical tuple tied to the same canonical record would justify `PASS_EXACT_GAMEOBJECT_PERSISTENT_KEY`.

The later offline exhaustion pass proved scheduler construction order, the exact
WAD-filename metadata lookup key, and six direct slot-release entries. It narrowed
the first missing join to the canonical override/final record pair into its loaded
type-`0x116` inner config. See
`docs/research/codex-offline-persistent-key-exhaustion.md`. Status remains
`BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY` and
`BLOCKED_EXACT_UNLOADED_STATE_ORACLE`.

## Tool

`tools/v0.10.5/trace-gow-registry-runtime-provenance.py` reuses the SQLite RIP-reference index, joins adjacent pdata chunks when control falls through, follows computed table addresses through registers, asserts exact lifecycle/scheduler anchors, and checks the canonical Raven record against the shipped WAD. It is read-only for game files and saves.
