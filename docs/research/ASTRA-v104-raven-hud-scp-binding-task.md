# GPT-6 Astra task: prove Raven compass HUD SCP binding and choose the correct topology

## Repository and branch

Repository: `Terru03/completionist-map-gow2018`

Work only on branch:

`codex/v104-raven-hud-research`

Pull latest before doing anything.

## Current status

The Raven map icon is working and must remain untouched.

The Raven compass HUD clone is **not safe for runtime testing yet**.

Read these first and treat them as authoritative current evidence:

- `docs/research/v104-raven-hud-physical-grammar.md`
- `archive/field-logs/completionist-v104-compass-hud-physical-groups.json`
- `archive/field-logs/completionist-v104-raven-compass-hud-three-payload-v3.json`
- `tools/v0.10.4/compass_hud_physical_groups.py`
- `tools/v0.10.4/inspect-compass-hud-physical-groups.py`
- `tools/v0.10.4/build-raven-compass-hud-three-payload-v3.py`
- `tools/v0.10.4/test_compass_hud_physical_groups.py`

The previous Astra pass proved the real Dock HUD physical topology:

- model group: 5 physical records, 1 payload
- prototype group: 5 physical records, 2 payloads
- root group: 3 physical records, 1 payload
- complete clone: +13 physical records, +4 payloads, +3 WAD_R_UI accounting

The fourth payload is:

`SCP_BoatDock`

- flags `0x18`
- 96 bytes
- first dword/type `0x10005`
- script class starts with `SCR_UI`
- sentinel ID `baaddbbad0baaddbbaaddbbad7baaddb`

The source prototype stores its model dependency as a zero-data link. The SCP payload is a separate direct member of the same prototype group.

The previous three-payload design is blocked unless script-sharing semantics can be proven.

## Primary objective

Determine **how local SCP payloads are bound to compass HUD prototype nodes** and use evidence to decide which topology is structurally correct for `goProtoCompletionistRavenHUD`:

1. **Shared-SCP topology**: new Raven prototype may safely reference/reuse an existing SCP resource without cloning a new `0x10005` payload, allowing the earlier +3 payload / +2 accounting design.
2. **Local-SCP topology**: the Raven prototype requires its own local SCP payload, making the correct full clone +4 payloads / +3 accounting.
3. A different topology, if the WAD evidence proves both assumptions wrong.

Do not force a preferred answer.

## Important existing evidence

From the physical-grammar proof:

- All five inspected stock compass peers have the same physical role layout.
- Their 96-byte SCP bodies are byte-identical.
- `SCP_BoatDock` sentinel ID appears on 2,057 payload definitions with 211 distinct bodies.
- 401 payload bodies match Dock's SCP body.
- Only three zero-data records use the sentinel ID in the current WAD, and those are associated with the inserted working Raven map chain.
- The working map path converting local SCP definitions to links is **not sufficient proof** that compass HUD prototypes can do the same.

## Research requirements

### 1. Characterise the local SCP binding model

Inspect a broad sample, not just DockPoint. Include at minimum:

- DockPoint
- FastTravel
- Valkyrie
- MAIN
- SIDE
- several additional compass/HUD prototypes if discoverable
- several non-compass `SCR_UI` prototype groups with the same physical grammar
- the existing working Raven map chain where SCP definitions were converted to links

For every relevant prototype, record:

- prototype resource name/ID
- prototype payload node table and any IDs/names associated with nodes
- local SCP record name/ID
- SCP bytes hash
- SCP first dword/type
- physical relative position inside group
- whether a zero-data SCP link exists instead
- any repeated names/IDs/body hashes elsewhere in the WAD
- whether binding appears to depend on scope, physical order, resource name, sentinel ID, body, prototype node data, or another field

Do not infer binding from names alone.

### 2. Inspect prototype payload semantics around the SCP relation

The previous pass found the prototype self-ID at `+0x3A8` and node-table information referenced from `+0x18`.

Reverse-engineer enough of this local structure to answer:

- Does the prototype payload explicitly identify its SCP child?
- Does it identify a script node by ordinal/order instead?
- Does the SCP name correspond to a node name or generated loader name?
- Is the SCP sentinel ID intentionally non-unique because group scope disambiguates it?
- Can a prototype resolve an SCP payload outside its own group?

Compare peer payloads byte-for-byte and field-by-field where useful.

### 3. Explain the three working Raven-map SCP links

Trace the current working Raven map chain and determine why these zero-data SCP links work:

- `SCP_MapIconDock`
- `SCP_CollidableSphere9`
- `SCP_flourishD1`

Do not merely note that the map works. Identify the structural relationship between those links, their resolved target definitions, containing groups, prototype/node data, and loader resolution.

Determine whether that mechanism is genuinely portable to `goProtoCompletionistRavenHUD`.

### 4. Build automated proof tooling

Add a read-only inspector and focused tests so conclusions are reproducible.

Prefer extending the existing physical-group module rather than writing a one-off parser.

Tests must cover at least:

- scope/order/name/ID observations used in the conclusion
- peer consistency
- Raven-map link resolution evidence
- collision/ambiguity cases for the sentinel ID
- byte-exact source WAD round-trip

Do not modify the live WAD during research.

## Decision gate

After research, explicitly choose exactly one result:

### A. `SCP_SHARE_PROVEN`

Use only if evidence proves that the Raven HUD prototype can safely reuse/share an existing SCP representation.

Then:

1. Document the exact resolution mechanism.
2. Implement the smallest structurally faithful Raven HUD clone.
3. Prove the exact physical-record, payload and WAD_R_UI accounting deltas.
4. If this returns to +3 payloads/+2 accounting, explain precisely why omitting the local SCP payload is valid.
5. Build an **offline-only** candidate WAD.
6. Reparse and byte-round-trip it.
7. Prove all stock records remain byte-identical except the explicitly required WAD_R_UI accounting fields.
8. Do not touch DCB until the WAD passes all offline structural checks.

### B. `LOCAL_SCP_REQUIRED`

Use if evidence shows local group scope/order is required, or if safe sharing cannot be proved and the complete authored grammar is the only justified topology.

Then:

1. Revise the design to the complete +4 payload / +3 accounting topology.
2. Clone the local SCP payload structurally correctly.
3. Decide whether its header name and/or ID must change, based on evidence rather than aesthetics.
4. Update WAD_R_UI `0x10005` count plus the proven `0x10001` and `0x20001` increments.
5. Build an **offline-only** candidate WAD.
6. Reparse, round-trip and verify exact populations/accounting.
7. Prove source Dock resources and existing Raven map resources are untouched.
8. Do not touch DCB until the WAD passes all offline structural checks.

### C. `SCP_BINDING_UNRESOLVED`

Use if evidence is still insufficient.

Stop cleanly and state exactly what ambiguity remains and what additional evidence would resolve it. Do not create a speculative candidate.

## Only after a WAD topology is proven

If and only if the offline WAD candidate passes every structural proof:

Build an offline `wad_r_perm.dcb` candidate that changes only the `CompletionistRaven` compass class `IconName` from DockPoint to:

`goCompletionistRavenHUD`

Expected hash from current research:

`45E5C7943749F81C`

Keep `InWorld_tMPIcon_Name` unchanged.

Then add a combined WAD/DCB verifier that proves:

- only intended DCB bytes changed
- Raven class remains UID-sorted/valid under the existing packed-class rules
- new `IconName` resolves to the new HUD root
- new root resolves to new prototype
- prototype resolves to new model
- model resolves to existing Raven material
- model still shares `MG_boatdock_0`
- root still shares `goProtocompassicons`
- all existing working Raven map resources are unchanged
- no stock DockPoint resource changed

Even after successful offline WAD/DCB construction, **do not install them or launch God of War**. Produce a final explicit runtime-readiness gate and exact local PowerShell command for the user.

## Safety constraints

Hard requirements:

- Never write into the God of War directory.
- Never launch God of War.
- Never modify saves, progression, marker state, or installed mod state.
- Preserve the live `r_ui.wad` SHA256:
  `9eb1f548de036eb56c031561a9b7665d71b54fe251d360d2a5b7c60e3d6ff3c3`
- Preserve all current working Raven map resources.
- Preserve all stock Dock resources.
- Do not weaken assertions simply to make a candidate build.
- Do not redefine payload/accounting terminology to satisfy an old acceptance criterion.
- Keep failed v1/v2/v3 builders as historical evidence unless a replacement runner explicitly supersedes them.

## Work style

Work autonomously through inspection, implementation, tests and reports.

Use the existing parser/helper and physical-group tooling where correct, but challenge assumptions if evidence contradicts them.

Commit logical milestones and push successful work to `codex/v104-raven-hud-research`.

At the end report:

1. chosen decision: `SCP_SHARE_PROVEN`, `LOCAL_SCP_REQUIRED`, or `SCP_BINDING_UNRESOLVED`
2. evidence supporting it
3. exact topology/counts
4. candidate WAD SHA256 if one was legitimately built
5. candidate DCB SHA256 if one was legitimately built
6. tests run and results
7. exact PowerShell command for local verification
8. whether runtime God of War testing is safe yet
