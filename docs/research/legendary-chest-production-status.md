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


### Third attempt 2026-09-22 — shared placement anchor diagnostic correction

Evidence commit:

`c780e3f9ff77d36c0994a6f28accddc5bfbf0f5b`

Static tests passed, but the live sweep stopped before enumerating registry objects
because the new diagnostic incorrectly required every physical placement record ID
to be globally unique.

Catalogue reality:

- 33 tracked Legendary Chests;
- 32 unique adjusted physical-placement anchors;
- exactly one duplicated placement-anchor group;
- shared generic placement record:
  `b6ff101a177e574eb1f404264111e71a`;
- affected rows:
  - `legendary_chest_ace99ef5472abcbac29bd2b396a3fdf3`
    (`xpl980_beachwaterfall.wad`);
  - `legendary_chest_d63295f244f330219b003c913c0dab69`
    (`peak720_summitascenthub.wad`);
- both use the generic placement name `gochestobj`;
- their complete physical scene paths remain distinct;
- all 33 complete physical scene identities remain unique.

Repair:

- placement anchors are now diagnostic many-to-many keys rather than acceptance
  identities;
- anchor hits preserve all candidate catalogue rows;
- exact acceptance still requires a unique complete physical scene path;
- the shared-anchor case is pinned by unit test.

This failure therefore does not weaken the exact-identity strategy; it confirms
that a single placement record is insufficient and the full scene path is the
correct discriminator.


### Fourth attempt 2026-09-22 — live registry diagnostic completed, residency/identity assumption rejected

Evidence commit:

`0eaf9b386f666ae2011641597d34570fde96097e`

This was the first corrected attempt to complete the enhanced live registry scan.

Result:

- registry 238 count: 49152;
- non-null objects: 18519;
- objects using the proven identity method: 18519;
- identity vectors reconstructed: 18519;
- reconstruction failures: 0;
- exact tracked Legendary resolutions: 0/33;
- physical-scene prefix matches: 0;
- adjusted physical-placement anchor hits: 0;
- raw physical-placement anchor hits: 0;
- process-memory writes: false;
- save/progression writes: false;
- game-file writes: false.

Interpretation:

The physical placement record chain is not present in the currently resident
registry identity vectors, so it must not be treated as a universal all-33
GameObject identity oracle. Unlike the Raven family, Legendary Chest physical
instances are stream/residency dependent and the one-process global-registry
sweep is the wrong production gate.

The exact authored WAD catalogue remains valid. This result only rejects the
assumption that every tracked chest can be identified from one currently
resident registry image.

### Staged checkpoint pivot

The already-proven Raven staged-WAD capture contains 425 staged records.

Cross-checking its records against the 33 tracked Legendary Chest rows proves:

- 32/33 tracked Legendary catalogue rows have their source WAD represented;
- every one of those 32 represented rows maps to a staged WAD carrier whose
  parsed string table contains the field `state`;
- only `xpl100_httk.wad`
  (`legendary_chest_890a24d24d2864a1567af691c615870f`)
  is absent from that particular capture.

This is the correct next authority layer because the checkpoint carrier can
preserve unloaded object state independent of physical GameObject residency.

New tooling:

- `tools/v0.10.5/analyze-legendary-staged-state.py`
- `tools/v0.10.5/run-legendary-staged-state-inventory-and-push.ps1`

The offline analyzer does not modify the Raven decoder. It reuses the proven
bounded staged-WAD framing/token rules and inventories, for each tracked WAD:

- exact `__subobjs` parent keys;
- parsed serialized GameObject registry/object hashes where present;
- every child state row containing a field named `state`;
- raw state token tag/payload/width;
- all sibling fields;
- exact field-name/value-tag schema signatures.

This inventory is deliberately non-authoritative: it does not yet claim which
state-bearing subobject is the Legendary Chest or what numeric/string state
means OPENED. The purpose is to identify the recurring standard chest schema
and exact serialized parent keys before any binding is accepted.


### Staged state inventory accepted 2026-09-22

Evidence commit:

`5f8709a4e6792b81c7e391ec2ef0b8ab759f2fef`

Capture:

`archive/field-logs/source-scans/legendary-staged-state-20260922-142029`

Result:

- tracked Legendary catalogue rows: 33;
- tracked source WADs: 27;
- rows represented by the frozen staged capture: 32;
- represented WADs: 26;
- absent row: the `xpl100_httk.wad` Legendary Chest;
- generic state-bearing subobjects inventoried: 244;
- distinct state-row schema signatures: 7;
- Raven decoder modified: false;
- game process accessed: false;
- save/progression writes: false.

The dominant exact schema is:

`{ state = <tag1 scalar> }`

Observed across:

- 206 serialized subobjects;
- all 26 represented tracked Legendary WADs;
- one record class key:
  `0x75E050AB149B4062`.

Every dominant-schema parent is a serialized GameObject save reference. Its
registry hash exactly equals the native case-folded WAD-stem hash for the
containing WAD.

Observed scalar bit patterns are:

- `0x3F800000` = 1.0;
- `0x40000000` = 2.0;
- `0x40400000` = 3.0;
- `0x40800000` = 4.0.

These values are preserved as enum-like state evidence only. OPENED semantics are
not yet claimed.

The catalogue's textual/composite
`physical_instance_guid.state_instance_guid` does not directly hash to any
dominant staged parent object hash under the native 0x401 byte hash. The save key
therefore remains the native GameObject identity hash, not the text component key.

### Current identity-resolution gate

All 33 tracked Legendary Chests share prototype loader ID:

`966624c84fc6b8590179bfd6c72c2086`

New tooling:

- `tools/v0.10.5/resolve-legendary-serialized-identities-static.py`;
- `tools/v0.10.5/run-legendary-serialized-identities-static-and-push.ps1`.

The resolver:

1. reads only shipped tracked Legendary WAD files;
2. walks exact record references around the shared prototype loader;
3. discovers candidate 16-byte prototype/object identity elements;
4. evaluates explicit chest scene-boundary grammars;
5. computes native 0x401 GameObject hashes;
6. compares them against the exact 206 dominant staged `state` parent hashes;
7. accepts only one unique candidate+grammar combination matching all 32
   represented tracked catalogue rows;
8. derives all 33 serialized GameObject identities from that unique solution.

The gate fails closed if the best result is less than 32/32 or if multiple exact
solutions exist. Even a successful identity resolution does not yet prove which
numeric state means OPENED.


### Static identity resolver performance repair 2026-09-22

The first execution of the static identity resolver passed the six preflight tests
but then spent more than ten minutes inside the WAD reference walk without
producing a resolver result.

A live process check showed:

- resolver PID: 20304;
- CPU consumed: 824.6 seconds;
- working set: approximately 219 MiB;
- process remained CPU-active rather than deadlocked;
- no evidence/result commit had reached the remote branch;
- remote head was still `e93fa97029f58303126fb4fe654cd4a8cd9b8817`.

Root cause:

- `refs_in_record()` tested a freshly sliced 16-byte window at every byte
  position in every traversed WAD record;
- the two-hop candidate walk therefore performed the expensive search in Python
  rather than in native code.

Repair:

- compile one exact multi-pattern bytes matcher from the WAD record-ID set;
- perform candidate searching in Python's C regex engine;
- retain one-byte advancement after a match so overlapping 16-byte identities
  remain observable, preserving the old exhaustive semantics;
- add an explicit synthetic overlap regression test;
- emit and stream per-WAD progress from the resolver runner.

This is a tooling-performance repair only. It does not alter the identity
grammar, staged checkpoint oracle, state semantics, Raven runtime, active saves,
or game files. The 32/32 identity gate remains unproven until the repaired
resolver completes and archives its result.


### Static identity resolver second performance repair 2026-09-22

The first optimisation, a compiled multi-pattern regex over WAD payloads, remained
unacceptably expensive. On the repaired run the resolver consumed about 205 CPU
seconds and was still inside WAD 1/27.

The reference walk was therefore removed from candidate discovery entirely.

Reason this is safe and stronger:

- the old payload walker only accepted a 16-byte value when that value was
  already an exact parsed WAD record ID;
- therefore every candidate the old two-hop graph walk could ever emit is
  already present in the parsed record table;
- the new resolver scores the superset of all exact record IDs from all 27
  tracked Legendary WADs;
- semantic record names are retained only as diagnostic evidence and never as an
  acceptance filter;
- acceptance remains exactly one candidate+scene grammar reproducing all 32/32
  represented staged GameObject hashes.

Scoring is also reduced to the necessary work:

- each row/grammar scene prefix hash is computed once;
- each prototype candidate is tested by continuing that hash with only the
  final 16-byte identity element;
- the smallest staged hash set is used as the first exact discriminator before
  wider validation;
- progress is emitted during both WAD inventory and candidate scoring.

A unit test now proves that the fast hash continuation is byte-for-byte
equivalent to hashing the full identity vector.

No Raven runtime files, active saves, progression state, or game files are
modified by this repair.
