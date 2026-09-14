# Object Checkpoint Persistence Oracle

## Status

Native dispatch and exact persisted key: **PROVED** for the supported executable.

Unloaded lookup through the Lua-visible root pickle table: **RUNTIME PROOF
PENDING, FAIL CLOSED**.

`UNLOADED_STATE_ORACLE` remains blocked until the handoff's complete runtime
acceptance set passes. This report does not change the production gate.

## Supported binary

- `GoW.exe` SHA-256:
  `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`
- Image base: `0x140000000`
- Reproducible scanner:
  `tools/v0.10.5/analyze-object-checkpoint-dispatch.py`
- Archived scan:
  `archive/field-logs/source-scans/object-checkpoint-dispatch-20260914-205500/`

The scanner rejects any other executable hash and verifies exact instruction
bytes at every cited site.

## Backward trace from `OnRestoreCheckpoint`

The native per-subobject restore routine begins at `0x1405AD4A0`. Its relevant
chain is:

1. `0x1405AD4BE` obtains the caller-selected root. Callers select either
   `__PickleTable` or `__SoftPickleTable`.
2. `0x1405AD51F` reads the root field `__subobjs`.
3. `0x1405AD597` loads the exact subobject's GameObject pointer from
   `[subobject+0x28]` and calls `0x14060B9C0` to push its Lua object token.
4. Native Lua table lookup obtains `__subobjs[objectToken]`.
5. When that value is a table, `0x1405AD5F3` dispatches
   `OnRestoreCheckpoint(level, subobject, savedInfo)`.
6. After the callback returns, `0x1405AD6B8` pushes the same object token and
   consumes that record from `__subobjs`.

This proves the callback's `savedInfo` is not selected by coordinates, catalogue
order, WAD filename, or RegionSummary count. It is selected by the exact
GameObject reference supplied for that subobject.

## Save-side symmetry

The save path independently confirms the identity:

1. `0x140174B78` loads `[subobject+0x28]` and calls the same token pusher at
   `0x14060B9C0`.
2. `0x140174B98` dispatches `OnSaveCheckpoint` for that exact subobject.
3. The returned object state is stored under that same token in `__subobjs`.

Thus the persisted record and restore callback share one native exact-object
key in both directions.

## Persisted key

`0x14060B9C0` constructs an opaque tagged GameObject token. For a GameObject
with valid-reference bit zero set at `+0x278`, the visible packing is:

```text
bank   = dword[object+0x284] & 0xFFFFF
flavor = (dword[object+0x278] >> 3) & 1
low    = word[object+0x280]
token  = (((bank << 1 | flavor) << 16 | low) << 1) | 1
```

`tools/v0.10.5/object_checkpoint_dispatch.py` reproduces and tests this packing.
The value is an engine object-reference token. It must not be relabelled as a
WAD record GUID without separate evidence.

Within this supported executable's checkpoint format, the stable persisted
identity is therefore:

```text
root.__subobjs[opaque exact GameObject token]
```

The engine's own object-reference resolver, not a mod-side spatial join,
resolves that token to a GameObject/subobject.

## Small read-only proof of concept

`tools/v0.10.5/unloaded-checkpoint-oracle-probe.lua` wraps the already-proved
Raven `OnRestoreCheckpoint` and scans before calling the original callback.
That timing matters: the current record and unresolved records have not yet
been consumed by the native routine.

The probe:

- obtains root environments with `_G` and Lua 5.1 `getfenv`;
- reads only `__PickleTable.__subobjs` and `__SoftPickleTable.__subobjs`;
- accepts only records whose `savedInfo.ravenKilled` is boolean;
- obtains exact identity through read-only GameObject `Level` and
  `GetDebugName`/`GetName` accessors;
- joins only the unique catalogue `(source WAD, native object name)` pair;
- uses `engine.GetAvailableWads()` only to prove that a returned exact record is
  non-resident;
- compares per-object results with read-only RegionSummary aggregates;
- emits unknown for missing, unresolved, duplicate-conflicting, or ambiguous
  identity.

The builder refuses duplicate exact identities and duplicate runtime aliases.
The runner makes no progression, quest, save, marker, streaming, or lifecycle
call. Normal game save activity is not suppressed.

## Runtime acceptance gate

The runner
`tools/v0.10.5/run-unloaded-checkpoint-oracle-probe-with-log.ps1` archives and
checks all required observations:

1. at least one exact record has `resident=false`;
2. Veithurgard exact catalogue objects return `false, true, true`;
3. Veithurgard exact count and independent aggregate both return `2 / 3`;
4. one second region has all exact per-object records and an agreeing independent
   aggregate;
5. unknown or conflicting state remains fail closed;
6. the installed Raven script is restored byte-for-byte after the run.

Until one capture passes every item, production behavior remains unchanged and
`UNLOADED_STATE_ORACLE` remains blocked.
