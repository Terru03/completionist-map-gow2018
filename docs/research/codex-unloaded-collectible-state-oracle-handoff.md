# Codex handoff: exact unloaded collectible-state oracle

## Mission

Find a **read-only, exact per-object completion-state oracle for unloaded collectible objects** in God of War (2018) PC, starting with Odin's Ravens and designed to generalize to Nornir chests/puzzle elements, Lore, Artefacts, and Legendary Chests.

Work only on branch:

`codex/all-collectibles-production-research`

Do **not** merge to `main`.

The production gate remains fail-closed until an exact unloaded-state bridge is proved.

## What is already proved

### Raven static identity

The strict Raven catalogue contains 53 physical Raven objects, with native labor target 51 and two physical surplus objects. Each catalogue row has exact WAD object-instance identity, world position, and RegionSummary parent.

Loaded Raven completion state is the local boolean:

`ravenKilled`

`precisionchallenge.lua` proves:

- `OnStart` hides the Raven when `ravenKilled == true`.
- `OnHitByWeapon` sets progression and then `ravenKilled = true`.
- `OnSaveCheckpoint` returns `{ravenKilled = ravenKilled}`.
- `OnRestoreCheckpoint(level, obj, savedInfo)` restores `ravenKilled = savedInfo.ravenKilled`.

### Exact Veithurgard runtime validation set

RegionSummary parent:

`RegionSummary_VF_Raven_Parent`

`game.QuestManager.GetQuestProgressAndGoal("RegionSummary_VF_Raven_Parent")` returns:

- progress = 2
- goal = 3

The three exact Veithurgard Raven objects restored individually as:

1. position `(-64.850898742676, 12.987384796143, 787.30694580078)` -> `ravenKilled=false`
2. position `(-127.96075439453, 15.577629089355, 690.07580566406)` -> `ravenKilled=true`
3. position `(122.60485076904, 17.374271392822, 679.21160888672)` -> `ravenKilled=true`

The three `OnRestoreCheckpoint` payloads were exactly one-field tables:

- `{ravenKilled=false}`
- `{ravenKilled=true}`
- `{ravenKilled=true}`

This independently matches RegionSummary `2/3`.

Inside the Raven gameplay script:

- `engine.CurrentlyExecutingObject()` -> `Level 'WAD_Xpl200_Funeral'`
- `engine.CurrentlyExecutingSubObject()` -> the exact Raven `GameObject`

Use this three-object set as the primary oracle validation fixture.

### RegionSummary aggregate query is solved

Supported Lua API:

`game.QuestManager.GetQuestProgressAndGoal(questId)`

Examples already captured:

- `RegionSummary_VF_Raven_Parent` -> `2/3`
- `Quest_Labor_KillRavens` -> `27/51`

`GetChildrenQuestIds` returns a genuinely empty table for the Raven RegionSummary and global Raven labor (`#=0`, `rawlen=0`, no `pairs()` entries). RegionSummary is aggregate-only, not a per-Raven quest tree.

Aggregate state is useful for validation/inference but is **not** the exact per-object oracle.

## Important dead ends — do not repeat blindly

### QuestManager

499 loose Lua files were inventoried. 24 QuestManager methods are used. No shipped QuestManager method provides per-collectible object state. `GetQuestProgressAndGoal` is aggregate. Marker/tracking/listener methods do not reconstruct existing cold state.

### Bare `GetCounter*` / `GetRef*`

A real native descriptor table exists with 309 function descriptors and handlers including `GetCounter*`, `GetRef*`, `ResolveGameObject`, etc. The table is genuine and dispatched by a `bsearch`-based internal evaluator.

However, direct/bare runtime lookup in `_G`, `game`, `game.Level`, and `game.QuestManager` returned nil for the `GetCounter*` / `GetRef*` names. `game.*` modules are protected native proxy tables and are not enumerable. Do not assume the descriptor VM is directly callable from ordinary Lua.

### `_G.__object_savestate` / `core.save`

Do not confuse `core.save` with the engine-level object-script checkpoint system.

`core.save.lua` is a 111-line auxiliary Lua save library. It owns a private `object_savestate`, has explicit `AddLoadObjectCallback` / `AddLoadSystemCallback`, and is used for library-owned state such as boss state machines.

Its `Restore(savestate)` does:

1. assign the supplied Lua savestate table to `object_savestate`;
2. publish `_G.__object_savestate` in that module environment;
3. invoke only callbacks that were already explicitly registered.

No external shipped use of `AddLoadSystemCallback` was found. `AddLoadObjectCallback` is used by explicitly registered systems such as the boss state machine. Ravens do not register with it.

Therefore this library is **not** the mechanism globally enumerating every object script `OnRestoreCheckpoint` payload.

Runtime attempts to read `_G.__object_savestate` from map UI and Raven gameplay contexts returned nil. `engine.DebugGetSubObjectEnvironmentRoot()` also returned nil in both contexts.

### Lua `debug` library

The GoW Lua runtime exposes no `debug.getupvalue`; the `debug` path is closed.

### Save-byte correlation

Frozen-save binary research found candidate runtime keys and aligned changed slots but no exact static GUID -> persisted record -> `ravenKilled` mapping. Do not promote aggregate byte correlations to completion truth.

## The native-engine target to trace now

The key unresolved mechanism is the one that performs this engine-level operation:

`persisted object record -> exact GameObject/subobject -> OnRestoreCheckpoint(level, obj, savedInfo)`

For Ravens, `savedInfo` is already resolved to the correct object and contains `{ravenKilled=<bool>}`.

Trace the engine path that constructs and dispatches this `savedInfo` table.

### Priority reverse-engineering plan

1. Find native xrefs / registration / dispatch related to the literal callback names:
   - `OnRestoreCheckpoint`
   - `OnSaveCheckpoint`
   - if useful, `OnScriptLoaded`, `OnStart`

2. Identify the native function that invokes an object script's `OnRestoreCheckpoint` with:
   - level
   - object/subobject
   - saved-info Lua table

3. Trace backward to the persistence lookup that retrieves the saved record for that object.

4. Determine the stable lookup key used by the engine. Candidate classes include:
   - persistent GameObject/subobject ID
   - WAD object-instance GUID / record identity
   - engine object UID/hash
   - level + subobject identity
   - another serialized persistent handle

5. Determine whether that lookup can be queried read-only for an object that is not currently streamed/resident.

6. If there is an existing native/Lua-exposed getter, prove it with the Veithurgard 3-Raven fixture.

7. If there is no exposed getter but the saved state can be observed at a global restore dispatcher, build the smallest possible read-only hook that captures `(stable object identity, savedInfo)` for restore records.

8. Only after a read-only bridge is proven, generalize it into a family-neutral resolver.

## Useful existing binary research

The repository already contains source scans/disassembly around native bindings. Reuse them instead of starting over.

Known native descriptor table:

- file offset `0x11C8100`
- VA `0x1411CA300`
- stride 32
- 395 records total
- first 309 function descriptors

Descriptor layout:

- `+0x00` function-name string pointer
- `+0x08` native handler pointer
- `+0x10` signature string pointer
- `+0x18` scalar hash/ID/metadata

Known examples:

- `GetCounter` handler `0x140841E50`, signature `i_s|i_i`
- `GetCounterChildrenCount` `0x140841D50`, `i_s|i_i`
- `GetRefBool` `0x140845700`, `b_s`
- `GetRefInt` `0x1408456C0`, `i_s`
- `ResolveGameObject` `0x14084F750`, `i_s`

The table is searched through a `bsearch` dispatcher around `0x1407B9920` / `0x1407B9968`. `0x140D49058` is **bsearch**, not qsort/registration. `0x140D49060` is qsort.

Do not spend the pass reproving this unless the object-checkpoint dispatcher genuinely intersects it.

Relevant archive folders include:

- `archive/field-logs/source-scans/native-binding-descriptors-*`
- `archive/field-logs/source-scans/native-binding-dispatcher-*`
- `archive/field-logs/source-scans/native-binding-table-xrefs-*`
- `archive/field-logs/source-scans/native-state-wrapper-disassembly-*`
- `archive/field-logs/source-scans/native-persistence-bindings-*`
- `archive/field-logs/runtime-captures/raven-gameplay-savestate-*`
- `archive/field-logs/runtime-captures/generic-counter-runtime-*`
- `archive/field-logs/runtime-captures/native-namespace-inventory-*`
- `archive/field-logs/source-scans/core-save-restore-dispatch-*`

## Desired production architecture

```text
Static catalogue row
  - family
  - exact physical identity
  - WAD / object GUID
  - world XYZ
  - region / RegionSummary parent
        |
        v
Generic exact state resolver
  |-- loaded object adapter
  |-- persisted/unloaded object adapter   <-- missing blocker
  `-- aggregate RegionSummary validation/inference
        |
        v
collected / uncollected / unknown
        |
        v
marker shown / hidden
```

Family state semantics already known or expected:

- Raven -> `ravenKilled`
- Nornir chest -> opened/completed state
- Nornir seals/bells/mechanisms -> broken/activated/`runeEnabled`-style state
- Lore -> discovered/read state
- Artefact -> collected state
- Legendary chest -> opened state

Unknown must remain fail-closed; do not silently treat unknown as collected/uncollected.

## Acceptance criteria for opening the unloaded-state gate

Do not mark `UNLOADED_STATE_ORACLE` PASS unless all are true:

1. A read-only method resolves a static catalogue object to an exact persisted completion value while that collectible object is not resident.
2. Identity is exact and deterministic; no nearest-coordinate, ordering, filename-only, RegionSummary-count-only, or heuristic matching.
3. The Veithurgard fixture returns the exact pattern `false, true, true` for the three known Ravens.
4. The three exact values agree with RegionSummary `2/3`.
5. At least one second WAD/region is validated to rule out a Veithurgard-only special case.
6. No progression/save writes are required to query state.
7. The resolver can return `unknown` safely when proof is unavailable.
8. Evidence and runtime captures are archived on the research branch.

## Deliverables expected from the Codex pass

- Native call-chain report for engine object checkpoint restore.
- Exact stable object identity/key used for persistence lookup.
- Read-only proof-of-concept query or restore-observer hook.
- Veithurgard validation against `false,true,true` and `2/3`.
- Second-region validation.
- Reusable code under `tools/v0.10.5/` or the appropriate runtime module.
- Automated/self-logging runner if a runtime test is needed.
- Updated `docs/research/all-collectibles-production-status.md` with proven vs inferred findings.
- Tests for any pure mapping/resolver logic.
- Commits pushed only to `codex/all-collectibles-production-research`.

## Do not do

- Do not merge to `main`.
- Do not claim exact cold-state support from RegionSummary aggregates alone.
- Do not call unknown progression mutators.
- Do not use save-file nearest-byte or nearest-coordinate heuristics as identity.
- Do not re-run bare `GetCounter*` Lua name probes without a newly proven namespace/bridge.
- Do not treat `core.save` as the engine's generic object-script checkpoint store unless new native evidence proves that connection.
