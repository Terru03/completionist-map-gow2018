# Legendary Chests Production Status

## Branch

`codex/collectible-legendary-chests`

Base:

`codex/all-collectibles-production` at the proven Raven production line.

Raven-specific runtime files are guarded against divergence from
`release/ravens-v0.10.5-proven`.

## Scope

This branch implements Legendary Chests only.

Do not add Lore, Artefacts, Nornir, procedural Niflheim rewards, or unresolved
Legendary-path chests here.

## Static production set

The existing audited catalogue is retained unchanged:

- raw Legendary-path physical rows: 64;
- tracked production Legendary Chests: 33;
- exact Muspelheim trial-reward exclusions: 27;
- unresolved nontracked rows: 4.

Only the 33 rows with:

- `native_classification=tracked_legendary`;
- `production_eligibility=tracked_collectible`;

are eligible for this family branch.

Their completion contract is:

- adapter: `interact_chest_standard_checkpoint_state`;
- field: `state == OPENED`;
- query policy: read-only;
- missing/ambiguous persisted state: fail closed / no marker.

All 33 tracked rows have distinct exact scene-identity sequences under the same
native GameObject identity transform rule already proven for Ravens.

## Gate 1 — exact GameObject identities

Implemented tooling:

- `tools/v0.10.5/legendary_chest_identity.py`
- `tools/v0.10.5/test_legendary_chest_identity.py`
- `tools/v0.10.5/capture-legendary-chest-gameobject-identities-readonly.py`
- `tools/v0.10.5/run-legendary-chest-gameobject-identities-readonly-and-push.ps1`
- `tools/v0.10.5/test-raven-frozen-baseline.ps1`

The live sweep:

1. verifies the exact authored WAD record IDs for every transform-chain element;
2. opens the GoW process with
   `PROCESS_VM_READ|PROCESS_QUERY_INFORMATION` only;
3. locates native GameObject registry 238;
4. reconstructs each object's identity vector with the already-proven native
   identity algorithm;
5. matches a chest only when its complete scene identity is exact and unique;
6. captures the runtime prototype identity element;
7. computes the stable WAD registry hash and object hash;
8. emits the 17-byte serialized GameObject payload needed by checkpoint state;
9. requires all 33/33 tracked chests to resolve before this gate passes.

No debugger, remote game-code call, process write, save-file access, progression
write, or game-file write is used.

## Next gate after 33/33 identity proof

Extend the staged checkpoint-carrier decoder without changing the Raven wire
contract.

For the 33 proven Legendary identities:

- parse the exact `state` field from the standard chest checkpoint table;
- map `OPENED` to `complete`;
- map a proven non-opened state to `remaining`;
- map missing, malformed, conflicting, or unproven state to `unknown`;
- validate the per-object result against RegionSummary aggregates, never replace
  per-object authority with aggregate inference.

Only after persisted-state authority passes do we build Legendary map markers,
filters, Mystic Gateway suppression, compass behavior, immediate-open removal,
save/load reconciliation, and the final targeted live proof.
