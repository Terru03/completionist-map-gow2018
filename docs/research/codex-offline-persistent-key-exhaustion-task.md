# Codex task — exhaust remaining offline paths before next live GoW capture

## Context

Work on branch `codex/all-collectibles-production-research`.

Current supported executable:

- `GoW.exe` SHA256 `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`

Canonical Raven target:

- instance GUID `95b9c644-4d47-9ac6-8207-b1829d02909b`
- WAD `alf355_chiseldungeon.wad`
- WAD SHA256 `2e66a927426e83d4e7f2d6a17d5a3fd1387b1ddd415b7a5c43dc0d96fd7f5268`
- canonical WAD record offset `0x32E3C60`
- zero-based physical record index `9633`
- final record ID `44c6b995c69a474d82b107829c90029d`
- progression field `ravenKilled`

Current status must remain fail-closed unless exact proof changes it:

- `BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY`
- `BLOCKED_EXACT_UNLOADED_STATE_ORACLE`

Already proved; do not repeat broad work:

- `__subobjs` key is GameObject full userdata whose payload `+0x08` is a packed runtime token.
- token formula:
  `1 | (registry_id << 1) | (flavor << 17) | (slot << 18)`
- save callback `0x5F96B0` serializes the exact runtime token; restore `0x5F95F0` decodes the same token and resolves through `0x4EF0B0`.
- no hidden stable GUID substitution exists in these callbacks.
- no-hint allocation reaches `0x4EF2B0` with registry ID and uses a cursor-based circular first-free allocator, slot 0 skipped.
- registry table is `0x22A98C0..0x22A9AC0`, 64 qwords.
- registry insertion is `0x4F37A2`; removal `0x4F35A5`.
- registry constructor sets cursor=0, live count=0, capacity=0x400, and zero-fills the 0x2000-byte bank.
- soft reset clears cursor but does not clear the bank/live count.
- WAD `+0xC3C` is registry ID.
- metadata records are 0xA8 bytes; existing record `+0x24` supplies registry ID; new record uses `record_index + 0x12`.
- canonical loader path is no-hint and scheduler-driven, not proved equal to raw physical WAD record order.
- canonical worker is `0x858320`; scheduler driver around `0x85AC27`, with outer/inner list traversal and call at `0x85AEE3`.
- previous static provenance result proved the canonical Raven physical record at index 9633 / offset 0x32E3C60 but did not bind it to the allocator event.
- live capture tooling exists at `tools/v0.10.5/capture-raven-scheduler-allocator-runtime.py` and `tools/v0.10.5/run-raven-scheduler-allocator-runtime-with-log.ps1`.
- first live attempt failed before `Debugger ready`; wrapper has since been changed to archive Python stderr. User cannot launch/debug the game right now.

## Goal

Use the remaining Codex budget to exhaust useful **offline/source-only** work that can narrow or possibly close `BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY`, without requiring the user to launch GoW.

Do not stop after one small finding. Work the following routes in priority order and continue until genuinely exhausted or budget-constrained.

## Route A — scheduler-list construction -> exact catalogue record

Trace **backwards** from the scheduler traversal and `0x858320` call to the code that constructs/populates the outer and inner runtime lists.

Required questions:

1. What exact structure is an outer node?
2. What exact structure is an inner node/item passed into `0x858320`?
3. Which fields in those nodes point back to WAD, descriptor, record data, prototype, override, or any stable source identity?
4. What functions allocate and insert those nodes into the outer/inner lists?
5. In what order are nodes inserted, sorted, shuffled, partitioned, or selected?
6. Is the LCG at `0x85847E..0x8584E0` choosing only a runtime variant, or does it alter object allocation order/identity?
7. Can the exact canonical Raven raw record / unique 164-byte payload / source offset `0x32E3C60` be followed into one scheduler item statically?
8. Can `(outer_index, inner_index)` for the Raven be derived from file/runtime-construction inputs without observing a live process?

Follow computed/indirect calls and pointer-field dataflow, not only direct xrefs. Use the existing SQLite research index and binary/WAD parsers where useful. Add a narrow tracer if needed.

A valid positive result must show a causal path from the exact canonical record bytes/offset to the scheduler item, not merely a shared object name or record ID.

## Route B — exact WAD -> metadata record -> registry ID

Continue the `0x82CF00` metadata-record provenance until the exact `registry_id` for `alf355_chiseldungeon.wad` is either derived or proved unavailable offline.

Required questions:

1. What creates the 0xA8-byte metadata record array and what stable input defines its record order?
2. What is the key used on the existing-record lookup path before `record +0x24` is loaded?
3. Can the WAD identity/path/name/hash or another stable WAD record be mapped to that key?
4. Is `record_index + 0x12` deterministic from a static table/file order? If so, identify the source and compute the exact index/registry ID for `alf355_chiseldungeon.wad`.
5. What does metadata record `+0x28` mean exactly, and can it help bind scheduler context/WAD identity?
6. Search all writes/readers of the metadata array base, count, capacity and key fields, including indirect/computed accesses.

If exact registry ID becomes provable, record it explicitly and add an automated source-only assertion for the target WAD.

## Route C — allocation-order reconstruction / history compression

Assuming Route A and/or B yield more identity, determine whether the target slot can be reconstructed without a live capture.

Required questions:

1. From fresh registry creation, which canonical object allocations enter this registry before the target Raven?
2. Are frees possible before the target event on a normal clean load path? Trace all relevant free/clear calls and their scheduling relation.
3. Does scheduler time budgeting affect only timing across frames or actual relative order?
4. Does the scheduler preserve deterministic linked-list order once constructed?
5. Can the pre-target occupancy/cursor state be calculated from a static sequence of scheduler items?
6. If only a subset of preceding objects lack stable identity, characterize that subset exactly rather than declaring the whole route blocked.
7. Look for a simpler invariant: e.g. the Raven is the Nth allocation within a freshly created target registry before any free; if exact and causal, that can be enough to derive slot.

Do **not** infer slot from physical WAD index `9633` unless an exact construction edge proves that mapping.

## Route D — frozen-save leverage if a partial token becomes available

Only after Routes A-C produce a concrete registry ID, slot range, allocation ordinal, or exact token candidate, revisit the existing frozen save evidence.

Use the two known save backups and existing save/pickle tooling. Search `__subobjs` keys/tokens and `savedInfo` payloads using the narrowed candidate set.

The goal is to bind the canonical Raven token to `savedInfo.ravenKilled` without brute-force story-telling.

A valid positive binding should require:

- exact token candidate from a causal GameObject path,
- exact `__subobjs` entry using that token,
- exact Raven checkpoint savedInfo payload/field semantics,
- consistency across the frozen saves where applicable.

Do not promote `PASS_EXACT_UNLOADED_STATE_ORACLE` from a probabilistic match.

## Route E — harden the live capturer offline

Review the current live capturer for constructor/startup failures that can be found without launching GoW.

The previous attempt died before `RuntimeCapture.run()` printed `Debugger ready`, so inspect every operation in `RuntimeCapture.__init__`:

- `load_target_record`
- `verify_image`
- `OpenProcess`
- Toolhelp module snapshot / `MODULEENTRY32W`
- path comparison
- ctypes function prototypes/restypes
- structure sizes/alignment, especially x64 `CONTEXT64`, `DEBUG_EVENT`, module/thread structures
- access masks and Windows error propagation

Add source-only/unit tests for anything that can be tested. If useful, add a **non-invasive preflight mode** that can validate static parsing, PE anchors, WAD target identity, ctypes sizes/contracts and environment assumptions without attaching to GoW. It must not pretend that process attach succeeded.

Keep the new stderr archive behavior.

## Deliverables

Make real repo changes rather than only describing findings.

At minimum:

1. Add/update one research document with exact proof, addresses, dataflow and status.
2. Add narrow tracer/probe(s) and tests for any new static edges.
3. Update the production research status only for claims actually proved.
4. Improve the live capture tool/preflight if you find a concrete robustness issue.
5. Run Python compile/tests, relevant full source test suite, `git diff --check`, and any binary-hash/anchor validations already used by this branch.
6. Commit and push all work to `codex/all-collectibles-production-research`.

## Acceptance gates

Only claim `PASS_EXACT_GAMEOBJECT_PERSISTENT_KEY` if the exact canonical Raven can be mapped causally and reproducibly to the same `(registry_id, flavor, slot)` after reload **without an unexplained dynamic-history dependency**.

A purely static derivation is acceptable if all inputs/order/reset semantics are proved. A repeated token observed in old evidence is not enough by itself.

Keep `BLOCKED_EXACT_UNLOADED_STATE_ORACLE` unless the exact Raven `savedInfo.ravenKilled` binding is also proved.

If a route remains blocked, report the **single narrowest missing edge** and the exact evidence ruling out broader alternatives. Do not reopen already-closed CodeSideLuaClass or serializer hypotheses without contradictory evidence.

## Important constraints

- Read-only for game files and saves.
- Do not write progression/collectible state.
- Do not patch GoW.exe on disk.
- Do not generate production runtime catalogue behavior from unknown state.
- Preserve existing untracked research index/archive files.
- Prefer exact xrefs/owners/dataflow over broad string scans.
- Reuse previous tools and archives rather than repeating solved work.
