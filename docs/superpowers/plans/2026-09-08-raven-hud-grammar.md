# Raven HUD grammar implementation plan

> Execute in this task. Use Superpowers debug, TDD, code review, and final verification steps. User authorizes commit/push; no mid-task approval needed.

**Goal:** Prove real Dock HUD group grammar. Build only if authoritative spec gates hold.

**Architecture:** Keep pinned byte-exact parser and failed v1/v2 tools unchanged. Add strict topology/role module, read-only inspector, focused tests, and v3 preflight. Use reduced class report to find peers. Derive counts from all group members, not just three named resources.

**Tech stack:** Python standard library, unittest, PowerShell, Git.

- [x] Add synthetic group tests in `tools/v0.10.4/test_compass_hud_physical_groups.py`. Test generic boundaries, links, extra SCP payload, nested duplicate names/IDs, exact clone changes, and rejection of malformed shapes. Run tests before implementation; inspect expected failures.
- [x] Add `tools/v0.10.4/compass_hud_physical_groups.py`. Derive roles from kind, scope, data, flags, and type. Clone complete groups; change only selected definition, proven self-ID slot, and selected local links/inline fields. Reject unsupported grammar.
- [x] Add inspector Python/PowerShell pair. Pin source hash, prove round-trip, inspect Dock/FastTravel/Valkyrie/MAIN/SIDE, report all physical rows and resolved link targets. Archive JSON in required field-log path.
- [x] Compare full clone counts against spec. Current evidence: 13 physical records, four nonempty records, extra SCP type `0x10005`. Verify full source population against accounting. Inspect existing script-link precedent and distinguish proven source grammar from inference.
- [x] Add v3 preflight and select it in active runner. If +3/+2 design conflicts with preserved grammar, archive blocked proof and stop before any candidate/DCB write, per spec. No silent SCP removal/conversion. If gates hold, continue all WAD/DCB checks in authoritative task.
- [x] Add safety/failure tests: wrong hash, outside-build destination, source/report overlap, malformed peer input, no candidate on blocked gate. Use repo-local paths; no recursive cleanup or live mutation.
- [x] Run fresh unittest suite, syntax checks, actual read-only inspector and v3 command. Inspect reports and source hash after run. Request independent code review, fix findings, rerun affected checks.
- [x] Write discovered grammar, both failed-builder causes, exact scope of proof, and runtime status in `docs/research/v104-raven-hud-physical-grammar.md`. Commit only source/docs/reports and push research branch.

Run focused tests with `python -m unittest discover -s tools/v0.10.4 -p test_compass_hud_physical_groups.py -v`. Run existing relevant tests with `python -m unittest discover -s tools/v0.10.4 -p "test_*.py" -v`.

Spec stop clause controls: if three-payload design itself lacks structural support, report actual required topology. Do not force acceptance or proceed to DCB. Local source evidence decides this branch.

Result: spec stop clause applies. Complete groups require +13 physical / +4 payload / +3 accounting. No WAD/DCB candidate built. Commit/push step completes with this delivery.
