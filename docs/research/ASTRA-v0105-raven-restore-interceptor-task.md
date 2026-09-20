# Astra High task: close the Raven restore-interceptor boundary

## Branch and goal

Work only on:

`codex/all-ravens-release-candidate`

Do not merge to `main`. Do not create unrelated collectible work on this branch.

The production goal remains:

- fresh saves show all 53 Ravens,
- old/advanced saves show only surviving Ravens immediately after load/map-open,
- a Raven disappears immediately when killed,
- persistence is reconstructed from authoritative checkpoint/save state without waiting for that Raven's WAD to stream,
- no save/progression writes.

The remaining blocker is exact unloaded Raven completion state.

## Start here

Pull the latest branch and read:

- `archive/field-logs/local-handoffs/raven-authority-handoff-20260920.md`
- `archive/field-logs/source-scans/thunk-persistence-hooks-20260920-202255/report.txt`
- `archive/field-logs/source-scans/checkpoint-restore-bridge-20260920-213242/report.txt`
- `archive/field-logs/source-scans/shared-rdata-restore-bridge-20260920-214151/report.txt`
- `archive/field-logs/source-scans/physical-slot-to-restore-20260920-202704/report.txt`
- `archive/field-logs/source-scans/lua-backing-allocator-primitives-20260920-201720/report.txt`
- existing custom-userdata / restore / GameObject-token research under `archive/field-logs/source-scans/`

Do not redo solved GameObject codec work, 53-Raven catalogue identity work, save-carrier framing, or the failed raw Lua backing-cache scan.

## New result that closes the Lua-hook detour

The latest scan found:

- `lua_files_scanned=500`
- `thunk_install_count=75`
- `unique_names=55`
- `semantic_thunk_install_names=0`

`core.thunk` is a real hook multiplexer, but there are no persistence / restore / pickle-facing semantic hook installs in shipped Lua.

Also already proved:

- `engine.SerializeHook` is not a restore interceptor. Its native handler intersects the solved GameObject token packer and belongs to serialization/token packing.
- the Lua backing-cache/raw-arena route is closed as an authority path.
- the remaining strongest route is the global custom-userdata restore machinery before GameObject userdata becomes opaque runtime tokens.

Therefore: do not spend this pass looking for another ordinary Lua `thunk.Install("OnRestoreCheckpoint", ...)` solution.

## Native targets already identified

Restore side:

- restore caller A: `0x5AEC9E`
- restore caller B: `0x5B2280`
- restore root: `0x7E9550`
- carrier descriptor: `0x7E7660`
- record dispatch: `0x7E7B60`
- userdata serializer/related path: `0x7E9190`

Checkpoint / active-slot side:

- physical slot transition entry: `0x66CB30`
- `checkpoint.SGA` path: `0x66ABD0`
- checkpoint stage A: `0x6687F0`
- checkpoint stage B: `0x669300`
- checkpoint stage C: `0x669B00`
- load slot core: `0x66B650`
- active checkpoint apply: `0x66C080`

Existing static call-index work found no direct indexed path from the physical-slot/checkpoint side to the restore functions. That strongly suggests an indirect dispatch, registered callback, vtable/interface edge, queue/job boundary, or data-driven handoff.

The prior shared-rdata candidates `0xD9E6B0` and `0xD9E4E8` have enormous xref surfaces and may be generic lookup data. Do not assume they are the bridge without proving ownership/semantics.

## Your task

Use Astra High reasoning to solve the **indirect native dataflow** between active checkpoint loading and the custom-userdata restore dispatcher.

### 1. Recover the indirect control-flow edge

Starting from both sides, identify the actual class/interface/registration mechanism that connects:

`checkpoint.SGA / active slot load -> persisted custom-userdata records -> restore root / record dispatch`

Pay special attention to:

- indirect calls in `0x669300`, `0x669B00`, `0x66ABD0`, `0x66B650`, `0x66C080`,
- vtable slot identities and vtable owners,
- callback registration tables,
- constructor/init code that installs those callbacks,
- job/event/message dispatchers,
- function-pointer arrays,
- state objects passed across the boundary,
- xrefs to restore-side functions that reveal class membership rather than direct callers.

Do not stop at “there is an indirect call”. Recover enough surrounding object layout / vtable / registration evidence to explain exactly why that indirect call reaches restore processing.

### 2. Find the pre-token interception point

The ideal boundary is where a persisted custom-userdata Raven record still contains:

- exact serialized/persistent GameObject identity,
- decoded or decodable payload containing `ravenKilled`,
- before the identity is converted into the opaque runtime GameObject token representation.

Identify the smallest stable function/structure where each record passes through.

For that point, document:

- function VA/RVA,
- caller and owner class/object,
- argument registers / structure fields,
- record bounds/length,
- identity bytes/fields,
- payload bytes/fields,
- whether all records for the active checkpoint pass through regardless of WAD residency.

### 3. Prove whether all Raven records are available at save/checkpoint load

The key product question is not merely whether a loaded Raven can restore itself.

Prove or reject:

> During load of the active save/checkpoint, does the engine process a global record stream containing Raven subobject records even when their WADs are not resident?

Use static proof first. If static proof is insufficient, build the smallest read-only runtime observer required to answer it.

### 4. If a runtime observer is needed

Create a self-contained, self-logging tool under `tools/v0.10.5/`.

Constraints:

- ReadProcessMemory / debugger-read / non-mutating observation only.
- No WriteProcessMemory.
- No code patching unless you can prove a genuinely observation-only debugger breakpoint route that does not alter game/save/progression state. Prefer hardware/debugger observation or existing logging surfaces.
- Never write a save.
- Never mutate progression.
- Never call unknown state-changing native functions.
- Do not launch the game automatically.
- Produce one PowerShell runner that archives its output and pushes it to this branch.
- If user interaction is required, stop after committing/pushing the runner and state the one exact command the user should run.

### 5. Turn the result into the Raven authority bridge if possible

If the pre-token record stream is solved, build a read-only decoder/observer that maps records to the already-solved 53 Raven catalogue identities and extracts `ravenKilled`.

Required behaviour:

- exact identity only,
- no nearest-coordinate matching,
- no RegionSummary-only inference,
- no filename-order inference,
- unknown remains unknown/fail-closed,
- no save/progression writes.

Use the existing solved GameObject/custom-userdata framing code instead of writing a parallel speculative decoder.

## Validation fixture

Use the already-proved Veithurgard fixture as the first exact state test:

`RegionSummary_VF_Raven_Parent` = `2/3`

Exact three Raven states:

1. `(-64.850898742676, 12.987384796143, 787.30694580078)` -> `ravenKilled=false`
2. `(-127.96075439453, 15.577629089355, 690.07580566406)` -> `ravenKilled=true`
3. `(122.60485076904, 17.374271392822, 679.21160888672)` -> `ravenKilled=true`

The authoritative per-object result must be exactly:

`false, true, true`

and independently agree with `2/3`.

If you can decode all 53 from the current advanced save, archive the complete exact result set.

## What counts as success

Best case:

1. exact indirect native path is documented,
2. a stable pre-token record boundary is identified,
3. active checkpoint load is proved to expose all persisted Raven records irrespective of WAD residency,
4. a read-only resolver/observer extracts exact `ravenKilled` for catalogue identities,
5. Veithurgard returns `false,true,true`,
6. at least one second region is validated,
7. the implementation is ready to feed map-open Raven filtering.

Useful partial success:

- a proven class/vtable/registration bridge that narrows the remaining runtime observation to one concrete function and argument layout.

Not success:

- another broad xref dump,
- another direct-call graph saying “no path”,
- another raw memory string scan,
- aggregate RegionSummary inference,
- a speculative vtable guess without ownership proof.

## Repo discipline

Commit and push every meaningful stage to:

`codex/all-ravens-release-candidate`

After each significant finding, update:

`archive/field-logs/local-handoffs/raven-authority-handoff-20260920.md`

with:

- new commit SHA,
- what was proved,
- what was ruled out,
- exact next unresolved boundary.

Do not force-push. Do not merge. Do not switch to the non-Raven collectibles branch.

Keep generated evidence under `archive/field-logs/` and reusable tooling under `tools/v0.10.5/`.

At the end, leave the branch in a state where the next person can continue from the handoff without repeating analysis.
