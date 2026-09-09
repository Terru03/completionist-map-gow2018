# Completionist collectible framework plan

## Goal

Add one registry-driven offline framework around frozen Raven production. Keep
Nornir Candidate 3 byte-exact and offline-only. Prove one synthetic collectible
can use same resource builder with no builder code edit.

## Hard gates

- Never write under installed game root.
- Never launch God of War or touch saves, progression, or marker state.
- Never edit frozen Raven files.
- Keep Raven WAD, DCB, Lua, identities, ownership, and GOPool facts exact.
- Keep Candidate 3 WAD and ten-file manifest exact.
- Keep stock map/HUD ModelGroups shared. Never edit opaque ModelGroup payload.
- Keep material `+0x20 = D595197B0961F689`; allow per-type `+0x10`.
- Unknown game identities and hooks stay `null` plus `unresolved` reason.

## Checkpoints

1. Add schema, registry, architecture doc, and failing contract tests.
2. Add generic registry loader, resource builder, GOPool builder, and validators.
3. Route Candidate 3 through generic builder; prove old bytes and normalization.
4. Add offline Lua marker-service contract and lifecycle adapter design.
5. Add synthetic WAD/GOPool proof, golden Raven checks, runner, and report.
6. Run focused tests, full offline proof, nearby regression tests, and final diff review.

## Test basis

| Risk | Observable proof |
| --- | --- |
| Raven drift | Exact live/file SHA checks plus resource/owner/GOPool inspection |
| Candidate 3 drift | Exact WAD SHA, ten-file manifest, parse/serialize, Raven normalization |
| MG mutation | Shared-link policy plus source/candidate payload equality |
| Resource alias | Registry duplicate checks plus reverse-owner graph checks |
| Hidden builder branching | Synthetic definition builds through same entry point |
| Unsafe write | Output-root guard rejects paths under game root |
| Fake discovery | Schema requires unresolved reason for null native/lifecycle fields |
| Non-determinism | Two independent builds have exact same WAD/DCB hashes |

