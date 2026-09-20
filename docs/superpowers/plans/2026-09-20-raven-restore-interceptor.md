# Raven restore interceptor plan

> Use Superpowers plan execution and independent code review. User asks autonomous work on current branch; no branch switch or approval pause.

**Goal:** Prove checkpoint-to-Lua restore ownership, then expose exact Raven state read-only if proof permits.

**Architecture:** Read known EXE and existing SQLite index. Follow concrete pointers, registrations, and state fields from both ends. Reuse carrier and GameObject codecs. Runtime observer only if static proof lacks live state; no game launch, save writes, or process writes.

**Tech Stack:** Python, Capstone, SQLite, PowerShell, existing carrier decoders.

## Stages

- [x] Read task and handoff; pull branch; note pre-existing unrelated edits.
- [ ] Recover owner: inspect full control flow across split unwind fragments, resolve selected virtual calls through constructor/vtable evidence, trace input buffer into `0x7E9550`. Save bounded evidence under `archive/field-logs/source-scans/`.
- [ ] Document smallest pre-token boundary: RVA/VA, caller, arguments, lengths, identity and payload relation. Prove or reject global unloaded-record coverage; label unknowns.
- [ ] If live proof needed, add one bounded read-only observer plus PowerShell archive/push runner under `tools/v0.10.5/`. Validate fixture decoding with existing framing, reject malformed/truncated/ambiguous state. Never infer false from absent records.
- [ ] Review tooling independently, run fresh relevant tests and syntax/build checks, inspect outputs, record requirement gaps.
- [ ] Commit/push each meaningful stage; update Raven handoff with evidence SHA, proof, exclusions, and exact next boundary. If user must load game, stop after runner push and give one command.

## Checks

- Pin executable SHA-256 `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`.
- Open SQLite with `mode=ro`; game EXE with read-only file access.
- Use bounds on every live pointer/count and reject inconsistent snapshots.
- Require exact 53-catalogue identity matching. Veithurgard must read `false,true,true`; RegionSummary `2/3` is only independent cross-check.
- Compile new Python; parse PowerShell AST; run focused behavioral tests. Static claims must cite exact instruction bytes/addresses.
- Keep existing map runtime intact until authoritative bridge proven. Report incomplete product requirements plainly.
- Before each push, check branch and staged paths. No force push, merge, or unrelated staging.
