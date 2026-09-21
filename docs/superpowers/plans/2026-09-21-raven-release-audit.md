# Raven release audit plan

Goal: Audit all 24 gates in `archive/field-logs/local-handoffs/astra-high-raven-release-audit-20260921.md`. Fix proven defects with tests first. Push only `codex/raven-release-adversarial-audit`; never merge RC.

Architecture: Keep native atomic authority, Lua kill overlay, and compass owner state separate. Keep existing five-file candidate and frozen binary pins. Use temp roots for install tests; leave real game files alone.

Tech stack: Lua 5.1 via lupa, Python unittest, PowerShell, MSVC C++20, CTest.

- [x] Read brief, inspect refs, create isolated audit worktree at baseline `5f0f593`.
- [x] Run baseline Lua/model/template tests. Lua 18 pass; model 23 pass; template 4 pass; binary build 11 skip due to source fixture mismatch. Resolve fixture from accepted local backups before final suite.
- [ ] Map visibility, event overlay, boundary freshness, compass intent, stock alias, teardown states. Trace mutating calls against every invariant.
- [ ] Independent review of native authority and packaging/proof/install helpers.
- [ ] Add deterministic regression tests for each proven defect. Run red tests before narrow fix. Run focused green suite; commit and push each finding/fix.
- [ ] Recover hash-verified source/candidate fixtures into ignored audit build tree. Never copy to real game.
- [ ] Run full Lua/model/candidate/template/proof, PowerShell parser/runner/transaction, clean MSVC build and CTest, safety scans. Archive actual output and skips/failures.
- [ ] Check latest field evidence against machine-verifiable live proof requirements. Treat unproved live behavior as release blocker; never claim fixture tests prove live behavior.
- [ ] Independent final change review; resolve findings; rerun full gates on final code.
- [ ] Record requirement matrix, exact results, safety, commits, limitations and merge readiness. Push report; verify remote tip and clean tracked tree.

State basis:

* Visibility = atomic killed set union positive session kills. Unknown starts visible; realm controls icons only.
* Periodic capture advances token even for same state. Normal snapshot cannot erase event kills.
* Boundary retains last-good visibility; clears Raven compass owner. Only strict post-boundary full capture can replace pre-boundary overlay. Failed baseline read must not label unseen cached capture post-boundary.
* Compass action needs exact collision object plus prompt UID. Latest add/remove intent must win native async settlement. Raven UID in stock query is alias. Foreign stock target works once Raven owner released.
* Proof refresh may change two Lua payloads and router/state metadata only. Three binary payload pins stay frozen. Install and rollback must restore all five files and exact prior owned DXGI pair.
