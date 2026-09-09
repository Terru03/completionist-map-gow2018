# Codex task: reconstruct the runtime-proven Raven recipe before Nornir Candidate 3

## Objective

Stop the incremental opaque-byte forensics on the retired Nornir Candidate 2. Reconstruct, from repository history and archived runtime evidence, the exact end-to-end construction that made the Raven map marker, compass HUD marker, and in-world marker work at runtime. Then derive an **offline-only** Nornir Candidate 3 from that proven Raven recipe.

The desired result is not another correlation audit. It is a historically attributable transformation recipe: every Nornir resource change must correspond to an exact Raven-success transformation or to Nornir-specific artwork/lifecycle data that is already proven offline.

## Non-negotiable frozen baseline

Branch family: `codex/v104-raven-production`.

The runtime-proven Raven production baseline is authoritative. Preserve it exactly.

Known frozen production hashes:

- `exec/dc/pc_le/wad_r_perm.dcb`: `85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5`
- `exec/dc/pc_le/wad_r_ui.dcb`: `765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d`
- `exec/wad/pc_le/r_ui.wad`: `5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60`
- `mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua`: `67d069a798417b631c271f48c129fb2083591b81a31859ab94769fbbb8b01c6b`
- Raven HUD GOPool: index 256, capacity 2
- Raven in-world carrier: `COMPASS_INWORLD_COMPLETIONIST_RAVEN`

Primary runtime proof:

- `archive/field-logs/completionist-v104-raven-full-compass-runtime-success.json`

Primary verifier:

- `tools/v0.10.4/verify-raven-production-state.ps1`

The Raven runtime proves:

1. custom map art works;
2. custom compass HUD art works;
3. custom in-world floating art works;
4. native distance/pathfinding works;
5. Add/Replace/Remove semantics work;
6. only one compass target is active;
7. simultaneous HUD + in-world use requires GOPool capacity 2.

## Nornir state that must be preserved

Nornir lifecycle logic has passed its offline gate but has **not** yet passed runtime because the visual/resource layer failed first.

Relevant proof:

- `archive/field-logs/completionist-v104-nornir-lifecycle-offline-success.json`

Known lifecycle contract:

- runic parent `challengeComplete` is observed/restored;
- the actual loot chest `OPENED` state is authoritative completion;
- `challengeComplete` without `OPENED` keeps the marker visible;
- `OPENED` suppresses the map marker;
- `OPENED` removes the active native compass target;
- no synthetic progression writes are authored.

Known Nornir resource plan/proofs include:

- `archive/field-logs/completionist-v104-nornir-resource-topology-success.json`
- `archive/field-logs/completionist-v104-nornir-resident-art-offline-success.json`
- `archive/field-logs/completionist-v104-nornir-material-reference-owner-audit-success.json`

## Candidate 2 is permanently retired

Do not rebuild, install, rehabilitate, or use Candidate 2 as a safety precedent.

Candidate 2 WAD SHA:

`96772dd9e36e1d3050ad936dbb9d8d8dfadb39ed2d7b4f74e400c2844877acef`

Runtime failure:

- Raven map marker disappeared;
- stock boat docks rendered custom Nornir chest art;
- game crashed on map open.

Rollback restored the exact pre-install state and the frozen Raven verifier passed.

Failure record:

- `archive/field-logs/completionist-v104-nornir-runtime-candidate2-failure.json`

Also inspect the earlier related failure:

- `archive/field-logs/completionist-v104-nornir-first-runtime-failure.json`

Candidate 2 attempted to isolate Nornir by cloning these stock model-group payloads under new top-level names/IDs:

- map donor `MG_mapicondock_0`
- HUD donor `MG_boatdock_0`

The dedicated Nornir payloads remained exact byte-for-byte donor clones. Runtime proved that this was not safe isolation.

Subsequent read-only audits established useful facts but did **not** decode an identity field:

- `audit-nornir-modelgroup-hidden-identity.py`
- `audit-nornir-modelgroup-payload-structure.py`
- `audit-nornir-modelgroup-peer-differentials.py`
- `audit-nornir-modelgroup-scalar-fields.py`

Do not continue the same sequence by merely classifying more opaque scalar bytes unless the Raven history itself requires it.

## Core question

**What exact transformation made Raven work, and how should Nornir reproduce that transformation without modifying or aliasing stock Dock resources?**

Do not assume that a dedicated Nornir model group is required. Do not assume that sharing the stock model group is safe either. Determine this from the runtime-proven Raven history.

A particularly important hypothesis to test from history is whether the Raven success path intentionally reuses stock `MG_*` resources while isolating model/material/prototype/root ownership elsewhere, and whether the Nornir “dedicated MG” direction was therefore conceptually wrong. Treat this as a hypothesis, not a conclusion.

## Required repository-history reconstruction

Use `git log`, `git show`, `git diff`, `git blame`, archived reports, generated builders, and transaction/proof scripts. Follow the full history, not only current documentation. Some research documents intentionally record blocked intermediate designs and must not be mistaken for the final working implementation.

At minimum reconstruct these stages:

1. last clean/pre-custom Raven state that can serve as a comparison baseline;
2. first working Raven custom map marker;
3. compass HUD resource discovery (`goboatdock` rather than the map GameObject chain);
4. first working Raven compass HUD art;
5. first working Raven in-world art;
6. GOPool capacity correction from 1 to 2;
7. final production adoption/freeze.

Known historical tracer commits include:

- `a775cf9` — Add compass HUD GameObject chain tracer
- `53ad400` — Add compass HUD GameObject chain trace runner
- `1c06a6c` — Fix compass HUD chain runner syntax check

Find the actual success/adoption commits around them rather than relying only on these known hashes.

## Required deliverable 1: Raven transformation ledger

Produce a machine-readable and human-readable ledger that states, for every file/resource changed from the selected pre-Raven baseline to the runtime-proven Raven production state:

- file path;
- exact resource name and ID/hash;
- original donor/source resource;
- whether the resource was copied, renamed, linked, shared, patched, or newly authored;
- exact byte fields or logical fields changed when determinable;
- DCB row/table changes;
- WAD physical group/member changes;
- model/material/model-group dependencies;
- prototype/root loader-name changes;
- SCP handling;
- GOPool row and capacity;
- Lua routing and target-selection logic;
- whether stock donor bytes/resources remained byte-identical;
- runtime proof that validates that stage.

The ledger must distinguish map, compass HUD, and in-world paths.

## Required deliverable 2: Raven-vs-Nornir failure comparison

Compare the runtime-proven Raven resource graph against:

1. Nornir first failed runtime candidate;
2. retired Candidate 2.

Identify the **first structural divergence** from the Raven recipe that can plausibly explain the boat-dock takeover. Prefer a concrete graph/topology/ownership difference over an opaque-byte theory.

Explicitly answer:

- Does working Raven have a dedicated map MG? If not, what exactly is shared and why does custom Raven art not leak to stock map docks?
- Does working Raven have a dedicated HUD MG? If not, what exactly is shared and why does custom Raven art not leak to stock boat docks?
- Where is the custom Raven material actually bound?
- Which physical group owns each local dependency record?
- Are MG records definitions, references, geometry/state containers, or something else in the working graph?
- Which loader keys are names, record IDs, local-scope links, type-table positions, or payload-local values?
- Which Candidate 2 assumption was unnecessary or incorrect?

If exact semantics are still unknown, graph ownership and byte-for-byte historical evidence are sufficient; do not invent field meanings.

## Required deliverable 3: Candidate 3 offline construction

Only after the reconstruction above is complete, construct an **offline-only** Candidate 3 that follows the proven Raven recipe as mechanically as possible.

Requirements:

- start from the frozen Raven production files, not from Candidate 2;
- preserve all frozen Raven resources and hashes where they are expected to remain unchanged;
- use existing proven Nornir artwork/material and lifecycle resources;
- introduce only changes attributable to the Raven recipe plus Nornir-specific IDs/names/art/lifecycle;
- no arbitrary edits to opaque MG scalar fields;
- no stock Dock/BoatDock resource definitions may be mutated;
- reverse-reference audit must prove stock Dock/BoatDock ownership unchanged;
- Raven resources must re-verify after offline assembly;
- candidate must round-trip/serialize exactly under the repository parser;
- produce a complete SHA manifest and structural diff against frozen Raven production;
- candidate remains blocked from installation until a separate transaction installer is reviewed.

Do **not** create or modify a runtime installer in this task.

## Required deliverable 4: failure-safe report

Create an archived report under `archive/field-logs/` describing:

- selected historical baseline and why;
- exact commits used to reconstruct each Raven success stage;
- Raven transformation ledger;
- Raven-vs-Nornir divergence;
- Candidate 3 file manifest and hashes if constructed;
- stock Dock/Raven preservation proofs;
- explicit safety flags showing no game/save/progression/marker writes;
- `runtime_install_allowed: false`.

If the exact Raven success recipe cannot be reconstructed with enough confidence to build Candidate 3, **stop** with a blocker report. Do not substitute another series of speculative byte-differential patches.

## Safety constraints

- No God of War launch.
- No writes under the installed game directory.
- No save writes.
- No progression writes.
- No marker-state writes.
- No Candidate 2 runtime use.
- No `-ForceRollback` or runtime transaction work.
- Do not weaken the frozen Raven verifier.
- Do not rewrite Raven production history.

## Working style

This should be one coherent repo-wide investigation rather than many tiny audit commits. Prefer doing the full history reconstruction, implementing the offline candidate if justified, running all relevant tests/audits, and then committing a small number of meaningful checkpoints.

Before declaring Candidate 3 assembled, be able to explain in one page **why Raven works, why Candidate 2 failed, and why Candidate 3 follows the working Raven topology instead of the failed topology**.
