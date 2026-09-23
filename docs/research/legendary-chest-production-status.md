# Legendary Chests Production Status

## RegionSummary link audit, 2026-09-23

`docs/research/legendary-region-link-audit.md` records the next static step.
All 33 tracked placement rows remain valid, but **0/33** have a unique native
chest-to-RegionSummary link. All 33 are unresolved for map ownership. The
stock Legendary open path asks `game.Map.FindPlayerRegion()` for the player's
current region, then updates a shared RegionSummary target. Target names and
counts in `mapmaster.dcb` and `quests.dcb` do not bind a chest GUID to that
region. An exact scan of 561 native DCB files found no physical GUID or
placement-record ID reference for these 33 chests. No map-side per-chest point
could be compared with the proven physical point. The JSON and CSV beside the
report keep each row's exact native source offsets and unresolved reason.
Runtime generation stays off.

## Placement audit, 2026-09-23

`docs/research/legendary-placement-audit.md` is the placement summary.
`legendary-placement-audit.json` and `legendary-placement-table.csv` hold the
full deterministic table. Read-only native WAD checks verified the physical
GUID, shared state carrier, WAD, rooted transform chain, and world position
for all 33 rows classified exactly as `tracked_legendary`. No placement row
is unresolved. The missing 34th identity is still a separate open problem.
This result does not clear the production gate below: chest-to-RegionSummary
bindings, marker assets, and runtime behavior remain unproved.

## Current static decision, 2026-09-23

`docs/research/legendary-static-gate.md` and its generated JSON are the
current authority. The 33 rows below are **candidates**, not cleared
production rows. `BLOCKED_FAIL_CLOSED`: 33/33 derived serialized keys,
32/33 exact frozen staged states, and 0/33 direct chest-to-RegionSummary
bindings. `stn200_lakeext` and `xpl300_stronghold` remain unresolved;
`cal500_runevault` and `cal740_leftwing` remain candidate Tyr rows without
direct bindings. Legendary marker/suppression and custom asset IDs are also
unproved. No Legendary runtime generation is enabled. The older gate and
runtime history below is kept as history only.

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
- tracked-candidate Legendary Chests: 33;
- exact Muspelheim trial-reward exclusions: 27;
- unresolved rows: 2, plus 2 provisional scope exclusions.

Only the 33 rows with:

- `native_classification=tracked_legendary`;
- `production_eligibility=tracked_collectible`;

are candidates for this family branch, subject to the current static gate.

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


### Static identity resolver completed, raw-record hypothesis rejected 2026-09-22

Evidence commit:

`e89118a3612c7dca285b45f6bcc5466f9944c1a3`

The direct-record resolver completed successfully as tooling and archived a
negative identity result in about 15 seconds.

Observed:

- 27/27 tracked Legendary WADs parsed;
- 211,370 unique raw record-ID candidates inventoried;
- four explicit scene grammars evaluated;
- 845,480 candidate+grammar combinations gated;
- no raw record-ID candidate survived the first exact staged-hash
  discriminator;
- therefore no raw record ID can be the missing final 16-byte identity element
  under any currently tested scene grammar;
- Raven runtime, active saves, progression state, and game files were untouched.

Diagnostic caveat:

The fast scorer stops a candidate at its first miss because only an exact 32/32
binding can pass. Therefore the reported failure value `best=0/32` is an exact
gate result, not a complete per-candidate partial-match census.

Next hypothesis:

The scene chain already uses the proven native record-ID identity transform,
which decrements byte 12. The failed candidate set contained raw record IDs only.
The resolver now includes both:

- raw record IDs;
- byte-12-decremented adjusted record IDs.

The shared Legendary loader is therefore tested explicitly in both forms:

- raw: `966624c84fc6b8590179bfd6c72c2086`;
- adjusted: `966624c84fc6b8590179bfd6c62c2086`.

A unit test pins this exact adjusted loader transformation. Acceptance remains
one unique candidate+grammar reproducing all 32/32 represented staged hashes.


### Adjusted-record suffix hypothesis rejected; runtime hash intersection next

Evidence commit:

`289a6c2eecc35299dc4fb8b522b695cb277785b5`

The second fast static sweep expanded the candidate set to both raw and native
byte-12-adjusted WAD record IDs:

- 407,157 unique candidate identity values;
- four scene grammars;
- 1,628,628 candidate+grammar exact-gate tests;
- no candidate survived the first staged-hash discriminator.

This rejects the model:

`authored scene chain + one raw/adjusted WAD record identity element`.

Additional structural confirmation:

- the first chest's `state_instance_guid`
  `b36ec130-4042-2d81-123a-9db40831d654`
  maps exactly, under the native four-byte-group identity encoding, to the
  byte-12-adjusted `gochestscript` record identity;
- its physical instance GUID maps the same way to the adjusted physical
  placement record identity;
- therefore the catalogue instance/record relationship is internally coherent;
- the unresolved piece is the native runtime parent/metadata-vector composition,
  not the catalogue GUID extraction.

New tooling:

- `tools/v0.10.5/capture-legendary-staged-runtime-identity-intersection-readonly.py`;
- `tools/v0.10.5/run-legendary-staged-runtime-identity-intersection-readonly-and-push.ps1`.

The probe reuses the proven registry-238 native identity builder and compares the
hash of every resident GameObject identity directly against the 206 archived
dominant staged `{state=<tag1 scalar>}` parent hashes.

For every exact hash intersection it archives:

- native identity elements in exact runtime order;
- builder parent/metadata-vector events;
- object+0x40 own identity;
- runtime slot/token;
- staged WAD and state value;
- overlap with all known Legendary authored identity elements.

This is read-only:
`PROCESS_VM_READ|PROCESS_QUERY_INFORMATION` only. Ravens remain frozen.


### Staged/runtime hash intersection negative; residency must be established

Evidence commit:

`85513b17d53c596710e55c670aab7f82fe4135b4`

The direct staged/runtime hash intersection completed cleanly:

- registry 238 count: 49,152;
- non-null GameObjects: 18,519;
- identity-method GameObjects: 18,519;
- native identities reconstructed: 18,519;
- reconstruction failures: 0;
- staged dominant state hashes tested: 206 unique;
- exact runtime object-hash intersections: 0.

Raven evidence confirms that the 64-bit serialized `object_hash` is the same
native 0x401 identity hash used by the live GameObject identity builder. The
negative result therefore does not invalidate the hash comparison itself.

The remaining ambiguity is residency: the archived staged checkpoint contains
state for unloaded WADs, while the live registry only exposes objects from
currently resident content. A zero intersection cannot distinguish
"checkpoint-only/unloaded target objects" from a deeper identity-structure
problem until at least one tracked Legendary WAD is proven resident.

New read-only tooling:

- `tools/v0.10.5/capture-legendary-live-wad-contexts-readonly.py`;
- `tools/v0.10.5/run-legendary-live-wad-contexts-readonly-and-push.ps1`.

It enumerates the already-proven 64-slot live WAD-context table, normalizes live
WAD names, and intersects them with the 27 tracked Legendary WADs. It always
archives the result, including the zero-match case, and performs no writes to
GoW, saves, progression, game files, or Raven runtime.


### Residency capture exposed registry-scoping bug 2026-09-22

Evidence commit:

`ec817ab980330f8fbced12d45ee901415b7652fa`

The first live WAD-context inventory reported zero tracked WADs only because its
normalizer required the live name to contain the literal `.wad` suffix. The
proved runtime context actually returns bare WAD stems.

The raw evidence already contains:

- `Xpl250_FuneralInterior` at live context index 9;
- live GameObject registry ID `241`;
- catalogue row
  `legendary_chest_d6d6acfe444f2ad10b49cea2ba85a1eb`;
- tracked source WAD `xpl250_funeralinterior.wad`.

This exposes the more important bug in the previous staged/runtime intersection:

- it scanned only registry `238`;
- in the same session registry `238` belonged to `Xpl200_Funeral`;
- the actually resident tracked Legendary WAD was registry `241`.

Therefore the zero-hit evidence in
`85513b17d53c596710e55c670aab7f82fe4135b4` cannot be used to reject the
identity mapping. It inspected the wrong live registry for the tracked chest.

Repairs:

- bare runtime WAD stems now normalize by appending `.wad`;
- the staged/runtime intersection now resolves the live WAD-context table first;
- every resident tracked Legendary WAD is paired with its actual live registry;
- only that WAD's staged dominant-state object hashes are compared against its
  corresponding live registry;
- the runtime token is encoded with the actual registry ID rather than a
  hard-coded 238.

The current loaded session already supplies one high-value target:
`xpl250_funeralinterior.wad -> registry 241`.

All probes remain read-only and the Raven runtime remains frozen.


### Correct live registry produced exact staged identity intersections

Evidence commit:

`acca00089c81848825aab40b8a064e15c688056a`

After resolving the actual live WAD registry instead of hard-coding registry 238,
the staged/runtime intersection succeeded.

For live `xpl250_funeralinterior.wad`:

- registry: `241`;
- non-null/identity-builder objects reconstructed: 5,429;
- staged dominant simple-state hashes in that WAD: 6;
- exact staged/runtime object-hash intersections: 6/6;
- reconstruction failures: 0.

The tracked chest is
`legendary_chest_d6d6acfe444f2ad10b49cea2ba85a1eb`.

Its strongest exact native identity match is live slot 880:

- runtime token: `0x000000000DC001E3`;
- staged/runtime object hash: `0x748BE60F37BAB846`;
- staged state raw: `0100008040` (numeric semantics still intentionally
  unclaimed);
- native identity vector:
  1. `d507eb21a5b18f45bc5265b60f30fd1c` = adjusted `goxpl250_ents`;
  2. `8e825d9cee977f42b76892e6e4509f4d` = adjusted
     `goxpl250_ents_nooffset`;
  3. `feacd6d6d12a4f44a2ce490beba185ba` = adjusted physical Legendary
     placement;
  4. `30c16eb3812d4240b49d3a1254d63108` = adjusted `gochestscript`;
  5. `947a7c50b25f004ea3365dd8dc232ee1` = live object+0x40 own identity.

The reusable `gochest_legendary_parent` is omitted because its adjusted record
identity equals `native.parent_prototype_id`, matching the already-proven Raven
self-prototype omission rule.

This establishes the runtime Legendary chest identity grammar:

`root owners -> physical placement -> gochestscript -> own identity`

with own identity element:

`947a7c50b25f004ea3365dd8dc232ee1`

The static 32/32 staged proof is now being rerun with this runtime-proven element
injected explicitly. State-value semantics remain unproven and are not promoted
by this identity result.

All capture/proof tooling remains read-only; Raven runtime remains frozen.


### Structural identity rule solved across all represented Legendary chests

The failed global-candidate run in
`78256ff319db43d647103dce1978d3e45c9d9d6e` did not invalidate the live
own-identity element. Its fast scorer stopped each candidate on the first
catalogue row that missed, so it could not reveal partial generalisation.

Direct per-row validation of the live-proven own identity element

`947a7c50b25f004ea3365dd8dc232ee1`

showed:

- 16/32 represented tracked chests matched immediately when every authored
  transform node except reusable `*_parent` nodes was retained;
- every remaining miss contained extra editor/organizational transform wrappers
  such as `gopickups`, `goloot`, `go____loot`, `gochests`,
  `godrainvaultsetup2`, or `go___drainsetup___`;
- an exact staged-oracle subset search was then run per row over the authored
  transform chain while preserving native root-to-object order;
- all 32 represented rows had exactly one matching subset;
- there were zero ambiguous rows and zero unsolved rows;
- every unique solution follows one common structural rule.

Resolved structural rule:

1. locate the physical chest placement using
   `native.placement_final_record_id`;
2. outside the physical placement, retain only true scene owners ending in
   `_ents`, `_ents_nooffset`, `_ents_offset`, or `_cbt`;
3. omit outer organizational wrappers such as pickup/loot/container grouping
   nodes;
4. retain the physical placement;
5. inside the physical placement, retain concrete nested chest objects such as
   `gochestobj` and `gochestscript`;
6. omit reusable nested `*_parent` containers;
7. apply the native byte-12 decrement to every retained authored record;
8. append the runtime-proven own identity element
   `947a7c50b25f004ea3365dd8dc232ee1`.

This rule reproduces exactly one staged object hash for every one of the 32
represented tracked Legendary chests.

The unstaged tracked chest
`legendary_chest_890a24d24d2864a1567af691c615870f` in
`xpl100_httk.wad` has the same structural layout:

`root ents -> ents_nooffset -> physical placement -> gochestscript -> own`

with the intermediate `gocontainers` wrapper omitted, so its identity is now
deterministic from the same rule.

Implementation updates:

- `legendary_chest_identity.py` now encodes the structural rule;
- the old 407k-candidate resolver has been replaced by a deterministic 33-row
  builder;
- the static gate now validates the 32 represented rows directly against the
  archived checkpoint oracle and derives the 33rd without live/process/WAD
  access;
- tests pin ordinary, organizational-wrapper, locked-root, live xpl250, and
  unstaged xpl100 cases.

State-value semantics are still deliberately separate and remain unproven.


### Structural proof rerun blocked only by obsolete tests

Evidence commit:

`a3b09f7fc1c237c267c5c627591eac3a93ff9fc9`

The deterministic structural resolver itself was not reached. The runner stopped
during the identity-test gate because two tests still referenced symbols from the
deleted 407k-candidate implementation:

- `resolver.continue_identity_hash`;
- `resolver.EXPECTED_PROTOTYPE`.

All new structural-rule tests passed, including:

- live xpl250 vector/hash;
- organizational-wrapper omission;
- locked-root chest-object retention;
- deterministic unstaged xpl100 derivation;
- unique scene identities.

The obsolete candidate-scan assertions were removed and replaced with a pinned
structural-resolver contract test. No identity rule or runtime evidence changed.


### Legendary serialized identity resolution accepted

Acceptance evidence:

`6ee6ebd6affa5fe0ddcbd7e815d28b526f80efec`

The deterministic structural resolver passed:

- identity tests: 11/11;
- tracked Legendary catalogue rows: 33;
- frozen staged represented rows: 32;
- exact staged bindings: 32/32;
- derived identities: 33;
- unique derived object hashes: 33;
- identity rule: `legendary_runtime_staged_structural_v1`;
- own identity element:
  `947a7c50b25f004ea3365dd8dc232ee1`;
- one unstaged row, `xpl100_httk.wad`, derived deterministically from the
  same structural rule;
- no process access, active-save access, progression writes, game-file writes,
  or Raven runtime changes.

Legendary serialized GameObject identity resolution is therefore closed.

Remaining research gate:

Prove the numeric semantics of the persisted `state` scalar with one controlled
normal-gameplay transition:

1. capture exact known Legendary states before;
2. open exactly one previously unopened tracked Legendary Chest normally;
3. allow the game to checkpoint/save normally;
4. capture exact known Legendary states after;
5. require exactly one tracked identity to change;
6. promote the after value to `OPENED` only from that controlled transition.

Tooling must remain read-only. The only save/progression write is the game's
normal action when the player opens the chest.


### Map-summary counts are not identical to physical tracked rows

User map evidence on the current almost-complete save reports River Pass Legendary
Chests as complete at `4/4`.

Native audit independently proves:

- `RegionSummary_LegendaryChest_Parent_Riverpass` target = 4;
- the physical Legendary catalogue currently has five tracked rows in the
  Riverpass namespace;
- frozen staged exact states for those five rows are four at scalar `4.0` and
  one scripted `gofinalchest02` row at scalar `2.0`.

Therefore raw physical-row count must not be used as the map-summary target.
The extra scripted physical row is not counted by the River Pass 4/4 summary.

This is also a useful but deliberately non-final calibration for the state
semantics experiment: scalar `4.0` aligns with all four map-counted River Pass
chests on a user-confirmed 4/4 save. It remains evidence only until a controlled
before/open/after transition proves OPENED.

Using the same comparison against native RegionSummary targets, the strongest
candidate incomplete regions in the frozen staged snapshot are:

- Peakspass / The Mountain: target 3, two rows at 4.0 and one `peak500_chimneytop`
  row at 2.0;
- BeachWaterfall: target 2, one row at 4.0 and one at 3.0;
- BeachMaze: target 1, row at 2.0;
- CalderaShores: target 1, row at 2.0;
- IslandArch: target 2, rows at 1.0 and 2.0;
- IslandClimb: target 1, row at 1.0;
- HTTK: target 1 but absent from the frozen staged capture.

This shortlist is for selecting a controlled test chest only; it does not promote
numeric state semantics.


### Temporary exact route marker for controlled OPENED-state test

To avoid manual navigation uncertainty, a reversible diagnostic marker is now
available for the candidate remaining Mountain chest:

- catalogue ID:
  `legendary_chest_ff46dfab43efcfc6f0f382a33e2b571d`;
- source WAD: `peak500_chimneytop.wad`;
- marker name:
  `Completionist_V105_LegendaryChest_ff46dfab43efcfc6`;
- native marker UID: `82300B1E715EF436`;
- world XYZ:
  `[-454.8589782714844, 1172.625, 858.6287841796875]`;
- realm/region: Midgard / Peakspass.

Diagnostic implementation deliberately reuses the already-proven Raven
map-resource and compass class only as a navigation renderer. It does not claim
the chest is unopened, does not infer completion semantics, and does not modify
Raven progression.

Files:

- `build-legendary-test-route-marker.py`;
- `install-legendary-test-route-marker-and-push.ps1`;
- `restore-legendary-test-route-marker-and-push.ps1`.

The installer:

1. requires GoW to be closed;
2. builds from the exact currently installed Completionist Map files;
3. adds one native mapmaster marker and one exact mapcoords entry;
4. appends a diagnostic map hook that displays the pin and routes it directly on
   the HUD compass when the Midgard map is opened;
5. backs up the three exact pre-test installed files before changing them;
6. records SHA-256 evidence;
7. does not read or write save/progression state.

The restore runner reinstates the exact backed-up bytes and verifies all three
pre-test hashes before removing the local diagnostic backup.


### Mountain test pivot: capture live chest GameObject IDs directly

Manual routing to `peak500_chimneytop` is no longer the preferred diagnostic.

Because the user is already loaded inside The Mountain, the stronger next step is
to interrogate the resident runtime state directly and capture the exact live
GameObject IDs for any tracked Legendary Chests currently loaded.

New tooling:

- `capture-live-legendary-chest-gameobjects-readonly.py`;
- `run-live-legendary-chest-gameobjects-readonly-and-push.ps1`.

The capture:

1. derives all 33 accepted Legendary object hashes from the solved structural
   identity rule;
2. resolves the live WAD-context table to the actual registry ID for every
   currently resident tracked Legendary WAD;
3. scans only those live registries;
4. reconstructs each native GameObject identity vector;
5. requires exact full-vector equality, not hash-only equality;
6. records the matched chest's live registry ID, slot, packed runtime token,
   object pointer, identity vector, and native builder metadata;
7. highlights Mountain/Peakspass matches separately.

This is strictly read-only:
`PROCESS_VM_READ|PROCESS_QUERY_INFORMATION`, with no game-code calls, process
writes, save/progression writes, game-file writes, or Raven runtime changes.

The temporary endpoint route marker may remain installed during this capture;
it modifies only map UI/static map-coordinate resources and does not affect the
Legendary chest WAD GameObjects being identified.


### Live Mountain GameObject capture and OPENED semantics closure

Live capture evidence:

`fec187519d09e3783b942aa00bc1081bb32419d5`

The current Mountain session exposed exactly one resident tracked Legendary Chest:

- catalogue ID:
  `legendary_chest_d63295f244f330219b003c913c0dab69`;
- WAD: `peak720_summitascenthub.wad`;
- live registry: `221`;
- live slot: `1189`;
- packed runtime token: `0x00000000129401BB`;
- object pointer: `0x7FF29F3CE670` in that capture;
- object hash: `0x3978566FB35C5EAD`;
- exact full native identity-vector match: yes;
- registry objects reconstructed: 7,721;
- reconstruction failures: 0.

This independently confirms the solved Legendary identity rule in a second
Mountain WAD using exact live-vector equality.

The same chest's accepted staged checkpoint carrier stores:

- field: `state`;
- raw scalar: `0100008040`;
- float32 value: `4.0`.

State semantics are now directly proven by stock game script evidence rather
than inferred from map counts.

The audited stock
`gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua`
defines:

`ENABLED = 1, DISABLED = 2, LOCKED = 3, OPENED = 4`

and its normal chest-opening path explicitly executes:

`state = states.OPENED`

For `chestType == "Legendary"`, the same path then updates the region's
Legendary Chest summary via:

`UpdateRegionSummary(currentRegion, "LegendaryChest")`

Therefore the persisted tag-1 scalar value `4.0` is conclusively the standard
Legendary Chest `OPENED` state.

Permanent proof artifacts:

- `archive/field-logs/source-scans/legendary-opened-state-semantics-20260922-161151/report.json`;
- `archive/field-logs/source-scans/legendary-opened-state-semantics-20260922-161151/report.txt`;
- helper constants:
  `OPENED_STATE_NUMERIC = 4`,
  `OPENED_STATE_FLOAT32 = 4.0`,
  `OPENED_STATE_RAW_HEX = 0100008040`.

Production completion rule is now:

- hide a Legendary Chest marker iff its exact persisted state is `4.0`;
- any missing, absent, undecodable, conflicting, or ambiguous state must not be
  treated as completed.

Legendary identity resolution and persisted completion semantics are both closed.
The next engineering phase is production marker integration and runtime
save/load validation.


### 2026-09-22 Legendary scope runner syntax repair

Two consecutive offline scope attempts were blocked before the actual scope
resolver executed.

Root cause:

- commit `3b50a5b093c5899e2be1ec8d6b984af9fe1d2ec4` inserted literal
  backslash-n text into `legendary_chest_identity.py`;
- the same OPENED-semantics promotion also left literal backslash-n text in
  `resolve-legendary-serialized-identities-static.py`;
- the scope runner's syntax preflight compiled the new scope resolver, helper,
  and test file, but did not compile the older static resolver that the test
  dynamically imports.

Repairs:

- `e11151e700258bc11f4520b6bbb98769483830a6` repairs all literal-newline
  corruption in `legendary_chest_identity.py`;
- `ea06aa2270ab86b5cb1dab2848896c5225501b8d` repairs the two malformed
  state-semantics blocks in the static identity resolver;
- `5e6bc060fbb411cd51b1c088527ac5d551837ae6` adds the dynamically imported
  static resolver to preflight and compiles each dependency individually with
  `py_compile.compile(..., doraise=True)`.

The failed attempts never reached the map-counted scope resolver and made no
game/save/progression changes.

### 2026-09-23 production eligibility audit

The accepted structural identity and `OPENED = 4.0` findings still hold.
An additional source review found that all 33 current map-counted rows are
*candidates* for production, since their chest-to-RegionSummary joins are
inferred: 31 by unique region/family, two by corrected target accounting.
The two Tyr assignments need a direct per-chest ownership edge before they
can count as proven production instances. `stn200` and `xpl300` still have no
positive native exclusion or tracked edge, though each now has an exact frozen
GameObject state match at `4.0`.

The read-only gate and evidence are in
`tools/v0.10.5/legendary_static_gate.py` and
`docs/research/legendary-static-gate.md`. It reports
`BLOCKED_FAIL_CLOSED`: 33 unique keys, 32 observed persisted states, zero
direct native parent bindings. No Legendary runtime output is authorized by
this static evidence. The earlier `EXACT_33_MAP_COUNTED_SCOPE_RESOLVED` report
remains a count reconciliation, not per-instance map membership proof.
