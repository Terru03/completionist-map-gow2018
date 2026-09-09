# Native Raven no-render research plan

**Goal:** Compare v0.10.3 proof with live v0.10.4 state; isolate regression without game launch or live writes.

**Architecture:** Reuse strict DCB/WAD readers and historical builders. Hash live inputs before/after; rebuild historical files only below ignored `build/`. Separate runtime observations from static checks. Prepare two-file A/B only if native coordinate/graph loss is confirmed.

**Tools:** Python standard library, existing binary readers, PowerShell, Git.

Start branch: `codex/v104-raven-hud-research`. Pulled HEAD: `5673e50043e8427abd318fdd56d7a40c4404a4eb`.

- [x] Pull branch; read task, historical/current logs, builders, cleanup/install manifests.
- [ ] Add `tools/v0.10.4/compare-native-raven-no-render.py`: inventory, historical reconstruction, full native joins, mapmaster byte scope, packed class lookup context, stock Dock HUD links/accounting, runtime claims, manifest provenance.
- [ ] Run read-only comparison; archive `archive/field-logs/completionist-v104-native-raven-no-render-comparison.json`.
- [ ] If missing native coordinate/graph confirmed, prepare exact historical pair below `build/v0.10.4/native-raven-no-render/`; add fail-closed install/rollback tool. Pin source, target, preserved files, branch, process state, and backup hashes. Never run live install.
- [ ] Test false-positive runtime claims, malformed/missing data, output containment, changed-source refusal, backup corruption, rollback refusal, partial failure recovery, and successful round trip on disposable fixtures.
- [ ] Write `docs/research/v104-native-raven-no-render-regression.md` answering all eight questions, confidence limits, exact control commands and observation checklist.
- [ ] Request independent code review using Superpowers review skill; assess frozen patch with Codex Security patch-risk skill. Fix material findings.
- [ ] Run fresh relevant tests/build checks and comparison; inspect outputs. Confirm live hashes unchanged. Commit useful tools/reports/research; push branch; verify remote HEAD.

Current hypothesis: cleanup preserved Raven mapmaster but restored stock mapcoords/compassgraph. Re-proof Lua checks only non-nil coordinate object, so accepts zero/default position. Archived log has nil WAD, zero XYZ, no manager verification. Missing data proven only after semantic reparse; sole visual cause requires user A/B observation.
