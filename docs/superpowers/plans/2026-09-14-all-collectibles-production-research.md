# All Collectibles Production Research Plan

## Goal

Build trustworthy native-data catalogues for Nornir chests and their real puzzle
elements, Lore Markers, Artefacts, and Legendary Chests. Reuse Raven marker
invariants only where data and state proof support them. Keep every unproven
family fail-closed. Do not launch God of War or write game/save/progression data.

## Baseline and safety

- Base commit: `abbeb1bc6a559336c2d92743e8bb70cd3ae15728`.
- Work branch: `codex/all-collectibles-production-research`.
- Read native WAD/DCB files and decompiled Lua only.
- Preserve the 53-entry Raven catalogue, Raven Lua, Raven builders, and tests.
- Generate only repository catalogue, audit, docs, and offline test/build output.
- Reject missing identity, bad transforms, duplicate UIDs, unknown state, cache
  reuse across saves, unsafe output paths, and progression-write APIs.

## Risk-led work

1. Extract native object carriers and full scene transforms for each requested
   family. Read script attributes, instance/script GUIDs, WAD identity, parent
   quest, subtype, and native parent/child links. Never classify by distance.
2. Join region-summary quest records to realm/region and native target counts.
   Report physical-versus-tracked differences instead of forcing guide counts.
3. Emit deterministic catalogue JSON plus strict schema and extraction audit.
   Keep raw native XYZ and use native-mapcoords projection metadata; add solved
   Midgard map coordinates as derived evidence where valid.
4. Record state oracles from native script save/restore code. Separate loaded
   state from unloaded/pre-install state. Gate marker generation and runtime-test
   readiness when exact unloaded per-instance state is unresolved.
5. Add a small family runtime model that preserves exact collision then UID
   ownership, numeric marker-ID normalization, one active target, stock/custom
   replacement, same-target removal, realm/filter behavior, Nornir parent-child
   suppression, checkpoint restore, teardown, retry bounds, and save cache reset.
6. Add deterministic offline build manifests and transaction/output safety tests.
   Do not install a candidate or modify Raven production files.
7. Write `docs/research/all-collectibles-production-status.md` with PASS/BLOCKED
   gates, counts, state evidence, exact blockers, files, and fresh test results.
8. Run focused family tests, full Raven tests, deterministic generation twice,
   static no-write scans, and repository diff review. Commit and push meaningful
   checkpoints only on the required branch.

## Completion rule

Static catalogue PASS needs native identity, source, and exact world position for
every discovered physical object. Runtime family readiness needs an exact
per-instance oracle that also covers already-completed objects before mod install.
Loaded-only proof is useful but not enough; such family remains hidden and marked
BLOCKED.
