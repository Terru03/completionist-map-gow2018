# Codex Sol task: deliver native 53-Raven snapshot into map/compass runtime

## Branch

Work only on:

`codex/all-ravens-release-candidate`

Commit and push every meaningful stage.
Do not merge to `main`.

## Read first

Mandatory:

- `archive/field-logs/local-handoffs/raven-authority-handoff-20260920.md`
- `docs/research/v0105-raven-native-bridge.md`
- `tools/v0.10.5/all-ravens-map-runtime.lua`
- `tools/v0.10.5/all-ravens-gameplay-events.lua`
- `native/raven-authority-bridge/src/authority_runtime.h`
- `native/raven-authority-bridge/`

Archived native-binding evidence to inspect, not rerun:

- `archive/field-logs/source-scans/native-binding-descriptors-20260914-160311`
- `archive/field-logs/source-scans/native-binding-registration-context-20260914-164815`
- `archive/field-logs/source-scans/native-binding-dispatcher-20260914-165955`
- `archive/field-logs/source-scans/native-binding-table-xrefs-20260914-161300`
- `archive/field-logs/source-scans/native-lua-binding-xrefs-20260914-065549`

## Solved — do not redo

Do not revisit:

- Raven GameObject codec/carrier;
- Raven catalogue identity mapping;
- staged WAD authority;
- absent-WAD=false proof;
- native 53-state decoder;
- DXGI load architecture;
- complete DXGI export forwarding;
- XInput;
- Steam bootstrap handling;
- schema-3 installer/rollback/recovery;
- package.loadlib;
- VFS/GetRef/save-root research.

V3 live proof already passed.

Evidence:

- commit `6023dd419959bcb0645d08a4a4259dfe56a7b07a`
- capture `archive/field-logs/runtime-captures/raven-native-bridge-load-proof-v3-20260921-130020/`

Exact accepted advanced-save snapshot:

```text
count=53
unknown=0
alive=26
killed=27
explicit=42
absentWadFalse=11
```

Native load state is closed:

```text
RAVEN_NATIVE_LOAD_AND_AUTHORITY_PROVEN
```

## Important live timing observation

V3 observed two valid generations:

boot/transient:

```text
generation=1
alive=53
killed=0
explicit=0
absentWadFalse=53
```

after advanced save restore:

```text
generation=2
alive=26
killed=27
explicit=42
absentWadFalse=11
```

Do not reject an all-alive snapshot based on shape alone because that is also the correct state for a true fresh save.

Instead, synchronize at the proper game/map lifecycle boundary: map-open/current-save readiness must consume the newest atomic snapshot then available.

## Existing Lua integration point

Do not redesign Raven map/compass logic.

`tools/v0.10.5/all-ravens-map-runtime.lua` already has:

```lua
_G.CompletionistMapV105ApplyPersistedRavenKills(catalogueIds, source)
```

It already:

- clears stale Raven state;
- applies an exact killed set;
- leaves unspecified catalogue Ravens visible;
- hides a tracked Raven if it is killed;
- resynchronizes current map icons;
- performs no progression writes.

The existing map lifecycle already calls `syncIcons(self, "map_create")` from the wrapped `CompletionistMapV100_CreateMapPin`.

The ideal delivery flow is:

1. on map create/open, obtain one atomic native Raven snapshot;
2. convert its killed=true entries to catalogue IDs;
3. call `CompletionistMapV105ApplyPersistedRavenKills(killedIds, source)`;
4. then run normal `syncIcons`;
5. retain existing loaded-Raven `ravenKilled` event path for instant kill removal.

## Preferred native Lua API

Preferred user-facing Lua shape:

```lua
local snapshot = CompletionistMapNative.GetRavenSnapshot()
```

Recommended returned shape:

```lua
{
  schema = 1,
  generation = <integer>,
  capturedTickMs = <integer>,
  count = 53,
  aliveCount = <integer>,
  killedCount = <integer>,
  explicitCount = <integer>,
  absenceDefaultFalseCount = <integer>,
  states = {
    ["<catalogue-id>"] = true|false,
    ...
  }
}
```

A smaller contract is acceptable if it is safer, for example:

```lua
generation, killedCatalogueIds = CompletionistMapNative.GetRavenSnapshot()
```

but it must still be one atomic generation and must preserve all 53 state semantics.

## Native binding evidence

Static evidence proves a real native descriptor/dispatcher system:

- 309 function descriptors;
- descriptor stride 32 bytes;
- function descriptor table VA `0x1411CA300`;
- sorted by descriptor field at +0x18;
- dispatcher searches the table through `bsearch`;
- registration/sort setup occurs around `0x1407BA450` / `0x1407BE5FC`;
- known native Lua functions such as `FindGameObjects` are real registered entries.

Do **not** mutate the existing 309-entry static table in place and do not overwrite an existing descriptor.

Preferred implementation:

- identify the legitimate runtime registration API/structure used after startup;
- register a separate Completionist Map function/namespace idempotently;
- preserve existing game descriptors;
- verify no name/hash collision before registration;
- register only after the relevant Lua/runtime system is initialized;
- keep registration outside loader lock.

If a namespace table is difficult but a safe bare native global is clearly supported, a narrowly named global such as `CompletionistMapGetRavenSnapshot` is acceptable, with a Lua wrapper constructing `CompletionistMapNative.GetRavenSnapshot`.

## If legitimate registration is not safely possible

Do not patch the static descriptor array or hijack an existing game function.

Instead use the already-loaded native bridge to integrate at a known map lifecycle/marker synchronization boundary.

Fallback may:

- observe map-open lifecycle;
- read the latest atomic native Raven snapshot;
- invoke/drive existing marker state using known map/compass data paths.

Fallback must not:

- write save/progression state;
- force-load WADs;
- patch existing native code bytes;
- overwrite unrelated Lua bindings.

## Lua-side changes

Modify `all-ravens-map-runtime.lua` minimally.

Required behavior:

- when map opens/creates, attempt one native authority refresh before icon creation;
- apply the exact killed set atomically;
- log native generation/counts;
- if native API is unavailable or not ready, do not destroy valid existing event-derived state blindly;
- no polling loop;
- no timer-based permanent polling;
- existing Raven event path remains intact;
- preserve map selection, captions, realm filtering, and compass behavior.

Recommended log markers:

```text
NATIVE_AUTHORITY_APPLIED generation=... killed=... alive=...
NATIVE_AUTHORITY_UNAVAILABLE reason=...
NATIVE_AUTHORITY_STALE generation=...
```

Avoid log spam.

## Generation rules

Lua should track the last applied native generation.

- apply a newer generation atomically;
- do not reapply the same generation unnecessarily;
- never apply an older generation;
- after save/checkpoint transition, map-open must be able to apply the new latest generation;
- do not infer readiness from alive/killed counts alone.

If the native API currently cannot distinguish “no snapshot published yet” from a valid snapshot, preserve the current `CompletionistMapGetRavenSnapshotV1` success/failure semantics.

## Immediate kill behavior

Do not replace:

`tools/v0.10.5/all-ravens-gameplay-events.lua`

Its existing exact quest+position identification and `ravenKilled` publishing remains the immediate runtime path.

Acceptance:

- kill a loaded Raven;
- marker disappears immediately;
- no native full-snapshot wait required;
- reopening map later reasserts authoritative state from native snapshot.

## Tests

Add deterministic offline tests for:

1. advanced snapshot:
   - 27 killed applied;
   - 26 visible;
2. fresh snapshot:
   - 0 killed;
   - 53 visible;
3. generation monotonicity;
4. stale generation ignored;
5. same generation not churned;
6. native unavailable fallback;
7. immediate event kill after native refresh;
8. map reopen reassertion;
9. tracked killed Raven compass cleanup;
10. realm/caption/selection behavior unchanged.

Native tests must verify:

- Lua-facing accessor reads one atomic `CompletionistRavenSnapshotV1`;
- exactly 53 states;
- no unknown state;
- no write APIs introduced;
- registration idempotent;
- collision/refusal behavior if namespace/function already exists.

## Windows CI gate

Before asking the user for a live delivery test:

- compile with MSVC warnings-as-errors;
- run native tests;
- run Lua/model tests;
- PowerShell syntax gate;
- security diff scan for process/save/progression write APIs;
- temporary workflow may be used and removed after green.

Do not use the user as the compile test.

## Live acceptance sequence

Only after offline/CI green, prepare one reversible live runner.

Advanced save:

- exact 26 surviving Raven map markers;
- 27 killed absent;
- exact Raven compass behavior preserved.

Immediate kill:

- kill one loaded alive Raven;
- that exact marker disappears immediately.

Map reopen:

- killed set remains exact after close/reopen map.

Fresh save:

- all 53 Ravens shown.

Also verify:

- captions/selection unchanged;
- realm filtering unchanged;
- compass add/remove/replace unchanged;
- `version.dll` untouched;
- schema-3 DXGI rollback exact;
- no save/progression writes.

## Stop condition

Stop only at:

```text
RAVEN_NATIVE_SNAPSHOT_DELIVERY_LIVE_PROOF_READY
```

meaning:

- safe native-to-Lua or fallback delivery mechanism implemented;
- no static descriptor overwrite;
- map-open consumes latest atomic snapshot before icon sync;
- immediate event kill preserved;
- offline tests green;
- Windows CI green;
- one reversible live proof command prepared.

Do not claim the public Raven release is complete until the live advanced-save + immediate-kill + map-reopen + fresh-save acceptance passes.
