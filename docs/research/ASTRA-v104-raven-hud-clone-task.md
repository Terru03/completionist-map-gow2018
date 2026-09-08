# GPT-6 Astra task: finish the Raven compass HUD clone correctly

Work only on branch `codex/v104-raven-hud-research` in `Terru03/completionist-map-gow2018`.

## Goal

Finish the Raven-only HUD compass GameObject resource path for God of War (2018) without touching the already-working Raven map icon or any stock DockPoint resources.

The desired HUD chain is conceptually:

```text
goCompletionistRavenHUD
  -> goProtoCompletionistRavenHUD
    -> MDL_completionistravenhud
      -> existing Raven material MAT_AE4AD85BB993F040
      -> stock Dock mesh MG_boatdock_0
```

The HUD root must keep the shared stock compass reference:

```text
root +0x54 -> goProtocompassicons
```

Eventually the Raven compass class in `wad_r_perm.dcb` should use `IconName = goCompletionistRavenHUD`, but do not build or patch the DCB until the WAD clone is structurally proven offline.

## Safety constraints

These are hard requirements:

- Do not launch God of War.
- Do not write to the live game directory.
- Do not modify saves, progression, marker state, or DCBs during WAD research.
- Do not mutate stock `goboatdock`, `goProtoBoatDock`, `MDL_boatdock`, its stock material/mesh, or `goProtocompassicons`.
- Do not modify the working Raven map chain, including `goMapIconCompletionistRaven` and its proven Raven material/textures.
- Candidate binaries must remain under the repo `build/` tree.
- Preserve reproducibility and archive a JSON proof report.

Current proven live `r_ui.wad` SHA256:

```text
9eb1f548de036eb56c031561a9b7665d71b54fe251d360d2a5b7c60e3d6ff3c3
```

Current WAD parse counts:

```text
physical records: 53811
payload records:  20415
WAD_R_UI total:   16802
0x10001 count:    1725
0x20001 count:    2073
```

The accounting research already proved that adding the desired three new payload definitions should change WAD_R_UI accounting by only +2:

- `goProtoCompletionistRavenHUD`: first dword `0x10001`, accounting +1
- `goCompletionistRavenHUD`: first dword `0x20001`, accounting +1
- `MDL_completionistravenhud`: first dword `0x1002000C`, not represented in the WAD_R_UI root type table, accounting +0

Important distinction: this means **three new payloads**, not necessarily three physical WAD records. Wrapper records, zero-data dependency links and group terminators may make the physical-record delta larger.

## Proven Dock HUD source chain

From the read-only compass HUD trace/reducer:

### Root

```text
name:         goboatdock
record index: 49156
payload idx:  18491
id:           e38da34945defe418b8be0bb6b985f12
flags:        0x3D
payload bytes:164
prototype ref at +0x0C: e38da34945defe418b8be0bb6a985f12
shared compass at +0x54: 502b9225361cf6449d8d85048f0b1a75
```

### Prototype

```text
name:         goProtoBoatDock
record index: 49151
payload idx:  18489
id:           e38da34945defe418b8be0bb6a985f12
flags:        0x3D
payload bytes:1184
```

Its model dependency is `MDL_boatdock`.

### Model

```text
name:         MDL_boatdock
record index: 49146
payload idx:  18488
id:           808e5817524559f5c65636ffc0fbc1a9
flags:        0x8E
payload bytes:80
```

Its local dependencies include:

```text
MAT_0C599DC8DC7E2170
  id 61ed20dc7a5567ba23016085750aacf2
  record 31804

MG_boatdock_0
  id c3f6b4c5a8270df607ea3e6e7f891292
  record 49144
```

The existing Raven material already verified as Dock-compatible is:

```text
MAT_AE4AD85BB993F040
id dac6009fd0f18caad2ed322463c3d0c8
```

The shared compass prototype is:

```text
goProtocompassicons
id 502b9225361cf6449d8d85048f0b1a75
record 49221
```

## Current intended Raven identities

```text
goCompletionistRavenHUD
  WAD spelling: gocompletionistravenhud
  id: f0029a68d9705e95a981aab8bff0c5b8

goProtoCompletionistRavenHUD
  id: b2a833d6144789e8099acf85e832d652

MDL_completionistravenhud
  id: 4a7911dc2db72cecaf6c187a66bfd11f
```

Before accepting these IDs, verify they do not collide in the current WAD. Keep them unless there is a concrete reason to replace them.

## Two failed builder attempts that must be understood, not papered over

### Failure 1: v1 assumed all dependencies were inline payload IDs

Command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\v0.10.4\build-raven-compass-hud-three-payload.ps1"
```

Failure:

```text
ValueError: Dock prototype model reference count changed
```

The source trace had already shown that some resource dependencies can be encoded as zero-data group links rather than literal 16-byte IDs inside the payload.

### Failure 2: v2 fixed dependency encoding but reused an invalid generic group-clone assumption

Current runner selects:

```text
tools/v0.10.4/build-raven-compass-hud-three-payload-v2.py
```

Failure:

```text
ValueError: MDL_boatdock: group did not contain wrapper + payload names
```

This comes from `clone_group()` in `build-raven-compass-hud-three-payload.py`, which assumes a resource group contains at least two records whose name exactly matches the payload name. That assumption is clearly false for `MDL_boatdock` and may be false for prototype/root groups too.

Do not simply change `renamed >= 2` to `>= 1`. Determine the actual physical group layout first.

## Primary hard task

Reverse-engineer the exact WAD physical group structure for the three Dock source resources and implement a clone operation based on the real structure rather than guessed naming rules.

### Phase A: physical group inspector

Create a read-only inspector, preferably:

```text
tools/v0.10.4/inspect-compass-hud-physical-groups.py
tools/v0.10.4/inspect-compass-hud-physical-groups.ps1
```

It should parse the current proven WAD using the existing byte-exact parser and emit a compact JSON report for:

- `goboatdock`
- `goProtoBoatDock`
- `MDL_boatdock`

For each resource, report its complete containing group span in physical record order, including at least:

- absolute record index
- relative index inside the group
- nesting depth relative to source group
- kind
- flags
- name
- id
- data size
- payload index if any
- parent/group relationship
- whether the record is the target payload
- whether it is a zero-data dependency link
- if a dependency link, which known target it resolves to

Also inspect the equivalent root/prototype/model groups for several peer compass classes, at minimum:

- FastTravel
- Valkyrie
- MAIN
- SIDE

Use the existing reduced class report to locate their resources. Compare layouts to distinguish invariant WAD grammar from Dock-specific details.

Archive the report under:

```text
archive/field-logs/completionist-v104-compass-hud-physical-groups.json
```

The inspector must not modify any game file.

### Phase B: derive the clone grammar

From Phase A, explicitly document what must change and what must remain byte-identical when cloning each of:

1. model resource group
2. prototype resource group
3. root resource group

Do not use record-name equality as the definition of a wrapper/payload/link role. Infer roles from kind, nesting, payload presence, IDs, source group topology and peer-class comparison.

A valid clone helper should preserve the complete source group grammar and perform only intentional changes such as:

- target definition name/ID
- dependency link name/ID when that link is actually local to the cloned group
- inline dependency ID only when the source encoding proves it exists inline

It must not rename unrelated nested records merely because they share an ID or name.

### Phase C: v3 offline WAD builder

Replace the v2 runner with a new builder revision. Keep v1/v2 as historical failed experiments if useful, but make the active runner use the new implementation.

The new builder should:

1. validate the source WAD hash and byte-exact round-trip
2. inspect/validate source group grammar before cloning
3. clone exactly the necessary three payload definitions with all required wrapper/link records
4. retarget prototype -> new model using the exact source dependency representation
5. retarget model -> existing Raven material using the exact source dependency representation
6. preserve model -> stock Dock mesh using the exact source dependency representation
7. preserve root +0x54 -> `goProtocompassicons`
8. retarget root +0x0C -> new Raven prototype
9. update only the proven WAD_R_UI accounting rows/totals
10. serialize, reparse and verify byte-exact candidate round-trip
11. verify exactly +3 payload definitions, while allowing the correct physical-record delta implied by the cloned source groups
12. remove the three new cloned groups from a reparsed copy, normalise only the known accounting bytes, and prove every original record is byte-identical to source
13. prove all stock Dock resources remain unchanged
14. prove the existing Raven map chain/material/textures remain unchanged
15. write candidate only under `build/v0.10.4/...`
16. emit a JSON proof report and commit/push only source/report changes to this research branch

Add focused automated tests for the group-role detection and clone transformation. Prefer tests that operate on parsed source-group fixtures or synthetic minimal groups, not only end-to-end assertions.

## Acceptance criteria for the WAD gate

Do not proceed to DCB work unless all are true:

```text
source WAD hash exact                       PASS
source parse/serialize byte exact           PASS
source group grammar understood             PASS
peer compass group comparison completed     PASS
candidate parse/serialize byte exact        PASS
new payload definitions exactly +3          PASS
WAD_R_UI accounting delta exactly +2        PASS
0x10001 count 1725 -> 1726                  PASS
0x20001 count 2073 -> 2074                  PASS
new root -> new prototype                   PASS
new root -> shared goProtocompassicons      PASS
new prototype -> new model                  PASS
new model -> existing Raven material        PASS
new model -> stock Dock mesh                PASS
stock Dock resources byte-identical         PASS
working Raven map resources byte-identical  PASS
all other original records byte-identical   PASS
live game files written                     FALSE
```

If the evidence shows the three-payload design itself is structurally invalid, stop and report the actual required topology instead of forcing these acceptance criteria.

## Secondary task only after WAD gate passes

Then build an **offline-only** `wad_r_perm.dcb` candidate that changes only the dedicated Raven compass class `IconName` from the current Dock HUD root to:

```text
goCompletionistRavenHUD
```

Use existing v0.10.3/v0.10.4 DCB tooling and archived reports to locate the correct Raven class and preserve all other class fields. Do not point `IconName` at `goMapIconCompletionistRaven`; that is the map GameObject chain and previously crashed after `ShowMarker` queued.

For the DCB candidate:

- source DCB must round-trip or be transformed by the already-proven exact writer path
- diff must be minimal and fully explained
- no live DCB write
- no save/progression/marker write

Finally create a combined offline WAD/DCB verification report proving that the Raven DCB `IconName` resolves to the new HUD root present in the candidate WAD and that the map Raven chain remains independent.

## Deliverables

Commit all successful research/tooling changes to `codex/v104-raven-hud-research` with clear commits. At the end provide:

1. root cause of both failed builders
2. exact physical group grammar discovered
3. files changed
4. tests run and results
5. WAD candidate/report paths and hashes if WAD gate passes
6. DCB candidate/report paths and hashes if DCB gate also passes
7. one exact PowerShell command David should run locally next
8. explicit statement whether it is safe to launch God of War yet

Do not ask for confirmation mid-task. Make the best end-to-end progress possible while preserving the safety constraints above.
