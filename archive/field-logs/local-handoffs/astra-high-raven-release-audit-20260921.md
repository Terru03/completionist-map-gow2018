# Astra High task — Raven release-candidate adversarial audit

Branch: `codex/raven-release-adversarial-audit`

Base: current `codex/all-ravens-release-candidate`

## Objective

Perform an independent, adversarial, release-blocking audit of the Raven-only Completionist Map implementation for God of War (2018).

Do **not** redo solved save/GameObject codec research. Do **not** broaden into other collectibles. Do **not** make cosmetic refactors. Focus on finding correctness, persistence, compass, rollback, proof, packaging, and safety defects that could still prevent a public Raven release.

## Required invariants

The final Raven implementation must satisfy all of these:

1. True fresh save: all 53 Ravens visible.
2. Existing/advanced save: only surviving Ravens visible.
3. Kill a loaded Raven: exact Raven disappears immediately.
4. Same-session map close/reopen: killed Raven remains absent.
5. Normal periodic native snapshots may never resurrect an immediate kill event.
6. Explicit save/load/checkpoint boundary:
   - preserve last-good state until a post-boundary full 53-Raven snapshot exists;
   - ignore pre-boundary/equal-stale snapshots;
   - first strictly post-boundary atomic snapshot may replace the session overlay.
7. Gameplay event path is positive evidence only:
   - `ravenKilled=true` may hide;
   - `ravenKilled=false` may never revive;
   - only atomic 53-Raven authority may mark alive.
8. Native snapshot generation is a freshness token:
   - every accepted 53-Raven capture advances generation, even if state is identical.
9. Rapid compass lifecycle:
   - Add Raven A -> Remove A -> Add A in one map-open session leaves Raven A tracked;
   - no boat/stock fallback;
   - no missing HUD target;
   - Raven's own marker ID appearing through stock query is treated as alias, not foreign stock target.
10. Add/Replace/Remove bottom-row text updates immediately and remains correct after base/native async settlement.
11. Selected Raven title/subtitle:
   - `Odin's Raven`
   - `Completionist Map`
12. Realm filtering remains correct.
13. Stock/Nornir compass behavior is not broken outside Raven ownership.
14. Save/checkpoint/load transition releases Raven compass ownership so legitimate stock targets work afterward.
15. No save writes.
16. No progression/quest writes.
17. No process-memory writes.
18. No static native descriptor writes.
19. Native transport remains loopback-only and rollback-safe.
20. Candidate install/rollback must be exact across all five files plus owned DXGI bridge.
21. Proof refresh must:
   - refresh only the two generated Lua payloads plus authority metadata;
   - freeze all three binary candidate pins;
   - leave tracked tree clean;
   - archive and push success/failure evidence.
22. Live proof must require machine-verifiable:
   - advanced authority apply;
   - immediate kill event;
   - map reopen;
   - explicit authority boundary;
   - post-boundary atomic snapshot apply;
   - fresh-save 0-killed/53-alive apply;
   - exact rollback.
23. No generated tracked test report may dirty the branch after successful gates.
24. All meaningful findings/fixes must be committed and pushed to this audit branch.

## Audit scope

Read and cross-check at minimum:

- `tools/v0.10.5/all-ravens-map-runtime.lua`
- `tools/v0.10.5/all-ravens-gameplay-events.lua`
- `tools/v0.10.5/raven_runtime_model.py`
- `tools/v0.10.5/test_all_ravens_lua.py`
- `tools/v0.10.5/test_raven_runtime_model.py`
- `tools/v0.10.5/test_all_ravens_build.py`
- `tools/v0.10.5/prepare-all-ravens-delivery-candidate.py`
- `tools/v0.10.5/refresh-raven-delivery-proof-and-push.ps1`
- `tools/v0.10.5/test-raven-native-snapshot-delivery-offline-gates.ps1`
- `tools/v0.10.5/test-all-ravens-transaction.ps1`
- `tools/v0.10.5/run-raven-native-snapshot-delivery-live-proof-and-push.ps1`
- `tools/v0.10.5/raven-native-bridge-runner-support.ps1`
- `native/raven-authority-bridge/src/**`
- `native/raven-authority-bridge/tests/**`
- `archive/all-ravens/all-ravens-release-candidate-offline.json`
- latest Raven handoff files and latest runtime capture evidence.

Also inspect any helpers transitively called by the install/rollback and native bridge paths.

## Method

1. Build a state-machine model for:
   - Raven visibility authority;
   - session kill overlay;
   - load/checkpoint boundaries;
   - snapshot generation/freshness;
   - compass ownership and stock alias handling.
2. Look for impossible/unsafe transitions, race windows, stale state, alias ambiguity, and teardown leaks.
3. Trace every call that can mutate:
   - Raven state;
   - compass state;
   - save/progression state;
   - game files;
   - native process state.
4. Check that all runtime invariants have actual regression tests, not just comments.
5. Add targeted tests for every uncovered race before modifying implementation.
6. Run:
   - Lua integration tests;
   - pure Python model tests;
   - candidate/template/proof tests;
   - PowerShell parser/proof tests;
   - native MSVC build + CTest;
   - safety token/API scan.
7. Audit release packaging/install/rollback for stale binaries, stale Lua payloads, proof mismatch, or dirty-tree generation.
8. Prefer narrow fixes over redesign unless a correctness invariant cannot otherwise be guaranteed.
9. Keep Raven branch free of unrelated collectible work.

## Findings policy

For each real finding:

- classify severity: release-blocking / high / medium / low;
- explain the exact failure sequence;
- cite the responsible code path;
- add a deterministic regression test;
- fix it;
- rerun relevant gates;
- commit and push.

Do not create speculative changes without a reproducible failure sequence or invariant violation.

## Final deliverable

Push all meaningful work to `codex/raven-release-adversarial-audit` and produce a final audit report containing:

- commits added;
- release-blocking findings fixed;
- remaining known limitations;
- exact test/gate results;
- safety statement;
- whether this audit branch is safe to merge/cherry-pick back into the Raven release candidate;
- if not safe, the exact blocker.

Do not merge to the Raven RC automatically.
