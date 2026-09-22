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


## Gate 1 first live attempt — failed safely, grammar corrected

First live attempt:

- evidence commit: `bc8e030aec5e4cdc2208bf01c845a8c45ee4b017`;
- capture:
  `archive/field-logs/runtime-captures/legendary-chest-gameobject-identities-readonly-20260922-140106`;
- registry 238 count: 49152;
- non-null GameObjects: 18519;
- identity-method GameObjects: 18519;
- successfully reconstructed identity vectors: 18519;
- reconstruction failures: 0;
- authored WAD record checks: 173/173 exact;
- tracked Legendary resolutions: 0/33;
- process-memory writes: false;
- save/progression writes: false;
- game-file writes: false.

The runtime registry reader was therefore proven healthy. The rejected assumption was
the first Legendary identity grammar.

The audited Legendary transform chain starts at a reusable nested state object:

1. `gochestscript`;
2. `gochest_legendary_parent`;
3. physical authored Legendary Chest placement;
4. scene owners out to the WAD root.

The first attempt incorrectly carried the nested reusable script side into the
physical GameObject scene identity. Raven chains do not have this same
physical-parent / reusable-state-subobject split.

Current diagnostic grammar:

- physical scene identity uses transform-chain rows 2..end only;
- rows are reversed to root -> physical object;
- each retained native record ID uses the already-proven byte-12 decrement;
- rows 0 and 1 are explicitly classified as nested reusable descendants, not
  physical scene records;
- acceptance is still conservative and has not been declared proven.

The next read-only capture additionally archives:

- every runtime object whose complete identity starts with the exact physical
  scene prefix;
- the remaining suffix identity elements after that prefix;
- exact adjusted physical-placement anchor hits;
- raw physical-placement anchor hits;
- suffix-signature frequencies across matching objects.

This guarantees that another failure will identify the missing native suffix
grammar rather than returning an unexplained 0/33.


### Second live attempt 2026-09-22 — static gate rejected before runtime capture

Evidence commit:

`20fa09e205fd2909af5f627db3059516ce75960f`

The runner stopped at the static identity tests before executing the registry
capture. No new runtime evidence was collected in this attempt.

Root cause:

- the corrected physical identity grammar intentionally removes the two nested
  reusable records;
- 10 of the 33 tracked Legendary Chests then have a valid two-record physical
  scene path (physical chest + direct scene owner);
- the unit test still required at least three physical scene records;
- those valid short chains were therefore rejected by the test rather than by
  the runtime model.

Repair:

- minimum physical scene length corrected from 3 to 2;
- all 33 physical scene identities remain unique;
- all 33 retain the exact
  `gochestscript -> gochest_legendary_parent` nested structure;
- runner now archives Python unittest and capture stdout/stderr separately so a
  future pre-runtime failure cannot lose its exact diagnostics.

This attempt does not count against the Legendary runtime identity hypothesis
because the live identity sweep was never reached.
