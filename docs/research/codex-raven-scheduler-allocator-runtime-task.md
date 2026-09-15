# Codex task: Raven scheduler -> allocator runtime binding

## Purpose

Close the one remaining edge for the exact GameObject persistent key by directly binding one known canonical catalogue Raven to its native runtime scheduler/allocator state on repeated clean reloads.

Work only on branch `codex/all-collectibles-production-research`.

This is now a **narrow runtime-provenance task**. Do not restart broad static archaeology and do not re-prove already frozen token/serializer/allocator facts unless needed to validate a runtime observation.

## Supported executable

- `GoW.exe`: `G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe`
- required SHA256: `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`
- research index: `.research-index\gow-caebcb027980.sqlite`

All RVAs below are for that executable.

## Read first

Read these before changing code:

- `docs/research/codex-registry-runtime-provenance.md`
- `tools/v0.10.5/trace-gow-registry-runtime-provenance.py`
- `tools/v0.10.5/test_registry_runtime_provenance.py`
- the existing self-logging runtime-capture/handoff helpers from the older Raven lifecycle work (use their worktree-safety, archive, failure-log, commit and push patterns where useful)
- current Raven catalogue entry for instance `95b9c644-4d47-9ac6-8207-b1829d02909b`

## Frozen facts — do not rediscover

### Persisted GameObject key

For a live GameObject:

```text
token =
    1
    | ((GameObject+0x280 & 0xFFFF) << 1)
    | (((GameObject+0x278 >> 3) & 1) << 17)
    | ((GameObject+0x284 & 0xFFFFF) << 18)
```

Inverse:

```text
registry_id = (token >> 1)  & 0xFFFF
flavor      = (token >> 17) & 1
slot        = (token >> 18) & 0xFFFFF
```

- `0x5F96B0` saves this exact qword.
- `0x5F95F0` restores this exact qword.
- `0x4EF0B0` resolves `(registry_id, flavor, slot)` back to a GameObject.
- There is no hidden GUID substitution layer in the serializer.

### Registry lifecycle

Global registry pointer table:

```text
0x22A98C0 .. 0x22A9AC0   # 64 qword entries
```

- `0x4F37A2` inserts a registry via computed table slot.
- `0x4F35A5` removes one.
- creation starts at `0x4F3660`.
- fresh constructor:
  - `+0x20` = zero-filled 0x2000-byte slot bank
  - `+0x28` cursor = 0
  - `+0x2C` live count = 0
  - `+0x30` capacity = 0x400
- soft teardown clears cursor but does **not** clear the bank/live count.
- same-ID registries can therefore be reused with prior occupancy.

Registry ID:

- WAD `+0xC3C` is the registry ID used by allocation.
- metadata record `+0x24` supplies it.
- new metadata-record path writes `record_index + 0x12` to `+0x24`.

### Allocator

Canonical object loads use no-hint allocation.

- `0x4EF4C0` selects the registry and tail-jumps to `0x4EF2B0`.
- registry fields:
  - `+0x20` slot bank
  - `+0x28` next-search cursor
  - `+0x2C` live count
  - `+0x30` capacity
- no-hint policy at `0x4EF2B0`: circular first-free from cursor, skip slot 0, choose first null entry, write object, advance cursor, increment live count.

### Scheduler / canonical load

- `0x85AC27` owns the time-budgeted runtime scheduler.
- outer runtime-list walk around `0x85AC80`.
- inner runtime-list walk around `0x85ACD5`.
- bounded processing `0x85AEC1..0x85AEEC`.
- call to canonical worker `0x858320` at `0x85AEE3`.
- worker resolves scheduler outer/inner list indices around `0x8583E2..0x85840F`.
- runtime variant/LCG path around `0x85847E..0x8584E0`.
- descriptor builder at `0x859BD6` uses slot hint `0xFFFFFFFF`.
- loader call at `0x859C0D` -> `0x856F50` -> no-hint allocator.

Physical WAD record order is **not** proved to equal scheduler allocation order.

## Exact target Raven

Catalogue instance:

```text
instance_guid = 95b9c644-4d47-9ac6-8207-b1829d02909b
final_record_id = 44c6b995c69a474d82b107829c90029d
wad = alf355_chiseldungeon.wad
canonical final offset = 0x32E3C60
zero-based physical record index = 9633
kind = 1
flags = 0x3D
size = 164
progression field = ravenKilled
```

The same record ID appears later in a zero-size record. **ID alone is not an acceptable binding**. The runtime event must be tied to the canonical record selected by offset/index or an equally exact ancestry proof.

## Goal

Produce a self-logging, version-locked runtime capture that proves this chain for the canonical Raven:

```text
catalogue record 9633 / 0x32E3C60
  -> exact scheduler entry/event
  -> exact allocator-entry registry state
  -> selected slot
  -> resulting live GameObject tuple/token
```

Then repeat from a clean reload and compare the two runs.

## Implementation requirements

Choose the least invasive reliable runtime-observation mechanism available on Windows for this repository. Reuse existing project runtime-capture scaffolding for safety/logging/archive/commit/push, but do not pretend human observation can prove native allocator state.

A debugger/breakpoint, read-only process-memory observer, or narrowly scoped temporary instrumentation is acceptable if implemented safely. Prefer observation over mutation. Any temporary breakpoint byte or injected hook must be restored exactly, must be version locked, and must not persistently patch `GoW.exe`.

The implementation must:

1. Verify exact `GoW.exe` SHA256 before using fixed RVAs.
2. Resolve ASLR/module base correctly.
3. Fail closed if any expected instruction bytes/register contract/record ancestry differs.
4. Never write progression, collectible state, map markers, or saves as part of the capture logic.
5. Never permanently modify the executable.
6. Preserve pre-existing tracked worktree changes and stage only its own archive/output paths, following the older self-logging capture pattern.
7. Archive failures as well as successes and push them.
8. Include source tests for parsing/comparison/token calculation and whatever parts of the capture protocol can be tested offline.

If an interactive two-phase capture is safer than one monolithic runner, implement it that way. Exact user steps must be printed by the wrapper. Do not require the user to manually copy register values.

## Required event data

For each target-Raven allocation event, record enough raw and decoded data to independently audit the conclusion.

### Exact record binding

Capture/prove:

- scheduler outer-list identity/pointer and current outer index
- scheduler inner-list identity/pointer and current inner index
- scheduler event/entry pointer
- every pointer/index transformation needed to bind that entry to the canonical WAD record
- canonical WAD identity
- canonical record offset `0x32E3C60`
- canonical physical index `9633`
- final record ID `44c6b995c69a474d82b107829c90029d`

Do not mark the event as the target merely because the object name or record ID matches.

### Allocator entry state

Immediately before the target allocation, record:

- `WAD +0xC3C` registry ID
- registry pointer
- actual global registry-table index containing that pointer
- registry `+0x28` cursor
- registry `+0x2C` live count
- registry `+0x30` capacity
- slot-bank pointer `+0x20`
- the circular scan path needed to prove the chosen slot (at minimum start cursor, tested occupied/free indices through the selected null slot)
- selected slot

If prior allocation/free events are necessary to explain the entry state, capture their compact sequence too rather than guessing from the final snapshot.

### Post-allocation GameObject

Record:

- allocated GameObject pointer
- `GameObject +0x278`
- `GameObject +0x280`
- `GameObject +0x284`
- decoded `flavor`, `registry_id`, `slot`
- computed persisted token qword

Cross-check these against the allocator inputs rather than trusting only one side.

### Run identity

Record:

- executable SHA
- module base
- timestamp
- capture-tool commit
- target catalogue identity
- enough world/WAD/load context to establish the two captures are comparable
- whether the registry was freshly constructed, reused, soft-reset, or fully recreated before the target event, if observable

## Two-run proof

Obtain two captures from two clean reloads of the same target context.

The tooling should generate a machine-readable comparison report answering:

- Was the exact canonical record bound in both runs?
- Was the registry ID identical?
- Was allocator entry cursor/live count/bank occupancy relevant to the selected slot identical?
- Was the selected slot identical?
- Was flavor identical?
- Was the final persisted token identical?
- What stable runtime inputs causally explain the identical tuple?

Merely seeing the same tuple twice is supporting evidence, not by itself enough to claim an offline-reconstructible key. The report must distinguish:

1. deterministic/reconstructible from stable catalogue/runtime-load inputs, versus
2. repeatable in the two observations but dependent on prior dynamic history, versus
3. different/non-deterministic.

## Pass/fail rule

Only emit:

```text
PASS_EXACT_GAMEOBJECT_PERSISTENT_KEY
```

if the canonical record can be deterministically tied to the same `(registry_id, flavor, slot)` after reload by a causal mapping that we can reproduce or compute for the supported game build.

Otherwise keep:

```text
BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY
```

and state the smallest remaining runtime edge or, if the slot is history-dependent in a way that makes offline reconstruction unreliable, explicitly recommend the architecture pivot instead of forcing a false key.

Always keep:

```text
BLOCKED_EXACT_UNLOADED_STATE_ORACLE
```

in this task. `savedInfo.ravenKilled` / frozen-save semantic binding is the next stage after the persistent key is genuinely closed.

## Expected repo outputs

Create, as appropriate:

- the runtime capture implementation under `tools/v0.10.5/`
- a self-logging PowerShell entrypoint/handoff under `tools/v0.10.5/`
- focused tests under `tools/v0.10.5/`
- machine-readable capture schema/output
- comparison helper for run A vs run B
- `docs/research/codex-raven-scheduler-allocator-runtime.md` documenting exact evidence and result

Runtime captures should archive under a clearly named path such as:

```text
archive/field-logs/runtime-captures/gow-raven-scheduler-allocator-<timestamp>/
```

Use the established project convention to commit and push capture archives, including failures.

## Validation

At minimum before handoff:

- Python compile passes for new/modified Python
- focused tests pass
- existing source-test suite remains green (document skips)
- `git diff --check` passes
- tool refuses wrong executable SHA
- tool self-tests token encode/decode and two-run comparison logic
- exact expected instruction anchors are asserted before runtime observation

## Handoff

If you cannot perform the live game interaction yourself, still complete and push the capture tooling and give one exact PowerShell command for the user to run. The wrapper must make any necessary in-game/reload steps explicit and archive/push the result automatically.

Do not ask the user to inspect addresses, registers, memory, or logs manually.

After the runtime evidence is captured, inspect it and continue the task if possible rather than stopping at tool creation. If the persistent key becomes genuinely proved, the immediate next research target is the exact frozen-save `__subobjs` entry for this Raven and the `savedInfo.ravenKilled` semantic binding.