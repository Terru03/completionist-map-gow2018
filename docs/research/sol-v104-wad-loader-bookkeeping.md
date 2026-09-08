# v0.10.4 WAD loader bookkeeping task

## Context

Continue from `docs/research/astra-v104-map-class-registry-findings.md` and commit `3c792feb5226c9578c828e6765a4067779903547`.

The previous research pass established that:

- `WAD_R_UI.GOPool` is a preallocation list, not a class registry or alias table.
- All pooled map classes are in use; there is no safe donor.
- The old grown Raven candidates are not runtime-safe.
- The old builders left the final payload name as `gomapicondock` and updated WAD type counts using file payload-index ranges rather than the payload's actual runtime type word.
- Full loader bookkeeping and exact crash cause remain unknown.

Do **not** build or install another runtime candidate until the bookkeeping gates below are proved.

## Goal

Reverse-engineer enough of the pinned PC loader to describe every structure that must change when a new `gomapicon*` final/prototype/model/material/texture resource is appended to `r_ui.wad`, and convert that understanding into read-only validation tooling.

Pinned executable SHA-256:

`caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`

Pinned stock `r_ui.wad` SHA-256:

`92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04`

Pinned stock `wad_r_ui.dcb` SHA-256:

`21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a`

Use the existing Capstone setup and `tools/v0.10.4/inspect-map-class-registry.py` as the starting point.

## Required questions

### A. WAD type accounting

1. Identify the exact loader code that consumes the WAD type table.
2. Prove what each row's `key`, `base`, and `count` mean at runtime.
3. Prove how a payload's first dword/type word selects or participates in allocation.
4. Determine whether adding one resource of type `0x10001`, `0x20001`, `0x30001`, or `0x40001` requires only incrementing the matching count and shifting later bases, or whether additional tables/budgets must change.
5. Trace any per-type heap-size, alignment, constructor, relocation, or allocation metadata used alongside the counts.

### B. Name-map/resource registration

1. Trace the code that inserts WAD resource names/hashes into the lookup maps used by the already-proved path around RVA `0x750920`.
2. Determine which name is authoritative for a final instance: WAD header name, payload name at `+0x1C`, both, or another table.
3. Determine how duplicate hashes/names are handled.
4. Determine whether zero-size links affect registration or only dependency/scope resolution.
5. Determine whether adding a new unique final/prototype/model/material/texture name requires any explicit count/index outside the physical WAD records themselves.

### C. Scope/dependency bookkeeping

1. Prove how group boundaries and zero-size links are interpreted.
2. Prove whether resource IDs must be globally unique, unique per WAD, or only unique within a scope/type.
3. Trace how prototype/model/material/texture dependencies are resolved and whether adding cloned scopes requires any parent/root count updates.
4. Determine whether the parent `goProtoNW633B8059` map-icon family has any hidden child count or index beyond physical group membership.

### D. Memory and budgets

1. Trace all root/heap counters in `r_ui.wad` that influence allocation.
2. Identify any byte budgets, object counts, per-type heaps, or warmup tables that a grown WAD must update.
3. Determine whether `wad_r_ui.dcb` GOPool capacity for a new class can be appended safely once the resource exists, including the memory estimate/warmup consequences of `Cnt`.
4. Find a principled Raven `Cnt` value based on live lifecycle needs, not stock marker counts.

### E. Old crash

Using the old visual candidate only as static evidence, enumerate every structural mismatch from stock expectations. Separate:

- proven-invalid bookkeeping,
- suspicious-but-unproven differences,
- fields now demonstrated safe.

Do not claim the exact crash cause unless a specific loader invariant is proved violated.

## Deliverables

Create or update read-only tooling under `tools/v0.10.4/` and write:

- `archive/field-logs/completionist-v104-wad-loader-bookkeeping.json`
- `docs/research/v0.10.4-wad-loader-bookkeeping-findings.md`

The report must include verified RVAs/instructions for all native conclusions, source hashes before/after, and explicit booleans for each gate.

Add unit tests for every parser/accounting rule discovered.

## Runtime gate

A new Raven WAD builder is allowed **only** if all of these are true:

- type-table semantics fully proved for every cloned resource type,
- all required counts/budgets identified,
- name-map registration path fully traced,
- header and payload names can be made internally consistent,
- resource/scope dependency bookkeeping fully accounted for,
- candidate passes all new static validators,
- stock resources remain byte-identical except explicitly required root/accounting structures,
- no donor stock class/resource is repurposed.

Otherwise stop with `runtime_test_ready=false` and document the missing gate.

## Safety

Read game files only. Do not launch the game, install WAD/DCB/texpack candidates, change `boot-options.json`, touch saves/progression, or alter the native Kratos/Omega marker.
