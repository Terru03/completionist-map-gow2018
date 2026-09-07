# Astra v0.10.4 map-icon chain

## 1. Status: PARTIAL

Work in progress. Start: 2026-09-07 15:38 UTC. Checkpoint due: 16:23 UTC.
Primary stop: 17:08 UTC. Hard stop: 17:38 UTC. Static reads only.

## 2. Executive conclusion

Nine extracted payloads omit key links. Raw WAD has zero-byte records with
16-byte resource IDs. GOWTool skips these in its extracted file index.
Do not build new WAD from extracted `.bin` files alone.

Task table has two wrong names. Raw stock WAD and extract both show entry
13912 = `SCP_CollidableSphere9`, entry 13913 = `SCP_flourishD1`.
No evidence yet for task's `SWG_MapIconDock` or `COL_MapIconDock` entries.

## 3. Nine-resource family map

Dock payload indices: 13906 GPU, 13907 MG, 13908 MDL, 13909 ANM,
13910 prototype, 13911 root SCP, 13912 collision-node SCP,
13913 flourish-node SCP, 13914 final instance.

Final instance payload `+0x0C..+0x1B` equals prototype header ID
`78240cfd16abdf479082d1653e9b6bee`.

## 4. Cross-family evidence

Pending full comparison. Vendor, Fight and Valkyrie have same ordered groups:
MDL plus zero-byte material/MG links; prototype plus zero-byte MDL/ANM links
and three SCP payloads; final instance group.

## 5. Material/texture linkage

Dock MDL group at WAD `0x2672850` has four material links:

| Link header | Material | Payload index |
| --- | --- | ---: |
| `0x2672960` | `MAT_F11E51F026F4596B` | 13715 |
| `0x26729C0` | `MAT_11A6DFE6C38CAD6D` | 13701 |
| `0x2672A20` | `MAT_F53695693934397F` | 13716 |
| `0x2672A80` | `MAT_0C599DC8DC7E2170` | 13699 |

Material 13699 group has texture links at `0x26388F0` (Dock diffuse) and
`0x2638A10` (Dock emissive). This material also serves `MDL_boatdock` at
`0x2E6B770`; stock material must stay intact.

## 6. Minimum clone set

Not yet proven. New identity needs own final instance, prototype/model route,
Dock artwork material group, and new texture identities. Shared stock geometry,
animation and generic effects may be reusable; loader semantics still need checks.

## 7. Required WAD/DCB edits

Preserve full WAD record stream, including zero-byte links and group delimiters.
WAD header size `0x60`, payload padded to 16-byte boundary. Source SHA-256:
`92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04`.
Source has 53,777 physical records; GOWTool index has 20,407 payloads.

GOPool second qword meaning still under study. Stock Dock row has `0x28`.
Do not claim this is WAD index or resource pointer.

## 8. Offline build algorithm

Pending linkage checks. First gate: parse full WAD, retain groups and IDs,
resolve all stock Dock dependencies, reserialize without edits and compare bytes.
No install or runtime test in this task.

## 9. Unresolved unknowns

Exact local ordinal fields; GPU pairing; minimum clone set; GOPool row value;
safe insertion point and new texture packaging remain under study.

## 10. Next smallest experiment

Read full material groups and compare payload fields across stock icon families.
Read stock executable RTTI for GOPool row type. Save results here near 45 minutes.
