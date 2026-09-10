# Raven Twin Stage A: map-only runtime gate

## Decision

Nornir Candidates 1, 2, and 3 are retired as construction inputs. Candidate 3 crashed when the map was opened in transaction `20260910T050816Z-d5f40327`; the transaction was rolled back, exact pre-install bytes were restored, and the Raven production verifier passed. The runtime evidence does not prove a root cause.

Candidate 3 was not an end-to-end Raven clone. Its builder rebuilt only `r_ui.wad` and `wad_r_ui.dcb`; it copied the other eight files from the old Nornir lifecycle candidate. The exact field record is archived in `archive/field-logs/completionist-v104-nornir-runtime-candidate3-failure.json`.

Stage A starts over from the current frozen, runtime-proven Raven files and asks one question only:

> Can God of War open the map with original Raven + Raven Twin using two distinct identities but the same proven Raven artwork?

## Scope

Stage A changes exactly four files:

- `exec/wad/pc_le/r_ui.wad`
- `exec/dc/pc_le/wad_r_ui.dcb`
- `exec/dc/pc_le/mapmaster.dcb`
- `exec/dc/pc_le/mapcoords.dcb`

It does not contain `wad_r_perm.dcb`, `compassgraph.dcb`, `mapmenu.lua`, `mainhud.lua`, chest Lua, compass classes, in-world carriers, lifecycle hooks, or Nornir artwork.

## Twin identities

| Role | Raven Twin value | Why changed |
|---|---|---|
| Marker name | `Completionist_V104_Veithurgard_Raven_Twin_01` | Proven marker identity must be distinct. |
| Marker UID | `2F530E7F3F156D90` | Folded hash of new marker name. |
| Map GameObject loader | `goMapIconCompletionistRavenTwin` | Proven loader identity must be distinct. |
| Folded loader hash | `3152371298304268` | Folded hash of new loader name; used by GOPool. |
| Map root record ID | `6f180d11ff68c6898595783fe704bad6` | Referenced WAD record identity must be distinct. |
| Map prototype record ID | `4dd998403d2a808cfa8dea637bc893f8` | Referenced WAD record identity must be distinct. |
| Map model record ID | `2be26e25ea5707b3f18ad71fef6ee7e8` | Referenced WAD record identity must be distinct. |
| Material record ID | `c2a6cfc678dd6f1d1beac86e5f6c4630` | Referenced WAD record identity must be distinct. |
| Diffuse file/user hash | `1C25CED771C6B311` / `D4DC4EA332F8F1BF` | Dedicated texture records permit later art-only replacement without topology changes. |
| Emissive file/user hash | `2F07426F7737EEB1` / `BECA3591D82B3DBE` | Dedicated texture records permit later art-only replacement without topology changes. |

The four general WAD IDs are deterministic SHA-256 namespace outputs. Texture definition and GPU IDs use the already-established structured file-hash/user-hash formats. All are collision-checked against the frozen Raven WAD.

## Field-change ledger

Every Raven-to-Twin payload/header difference is assigned one of the required classes. The generated JSON proof contains serialized-record byte spans for every row.

| Structure | Changed field | Class | Reason |
|---|---|---|---|
| Texture GPU records | Record name and ID | known identity | Dedicated Twin texture records. |
| Texture GPU records | Resident payload | unchanged | Exact Raven pixel payload. |
| Texture definitions | Record name and ID | known identity | Dedicated Twin texture records. |
| Texture definitions | `+0x9C` user hash | known local reference | Points definition to Twin GPU identity. |
| Material group | Boundary/payload record name and payload record ID | known identity | Dedicated Twin material record. |
| Material group | Diffuse/emissive dependency names and IDs | known local reference | Points material at Twin texture definitions. |
| Material payload | Every byte, including `+0x10` and `+0x20` | unchanged opaque donor field | Role remains unproven; copied exactly from Raven. |
| Model group | Boundary/payload record name and payload record ID | known identity | Dedicated Twin model record. |
| Model group | Material dependency name and ID | known local reference | Points model at Twin material. |
| Model payload | Every byte | unchanged opaque donor field | No scalar or ModelGroup mutation. |
| Shared `MG_mapicondock_0` | Existing records and payload | unchanged opaque donor field | Twin adds only a zero-data reference; stock data-bearing payload is untouched. |
| Prototype group | Boundary/payload record name and payload record ID | known identity | Dedicated Twin prototype record. |
| Prototype payload | Embedded prototype ID | known local reference | Established prototype self-reference. |
| Prototype group | Model dependency name and ID | known local reference | Points prototype at Twin model. |
| Root group | Boundary/payload record name and payload record ID | known identity | Dedicated Twin root record. |
| Root payload `+0x0C` | Prototype ID | known local reference | Points root at Twin prototype. |
| Root payload `+0x1C` | 56-byte loader name | known identity | Embeds Twin loader name. |
| Parent scope | Root dependency name and ID | known local reference | Registers Twin root beside Raven root. |
| WAD heap/type data | Counts, bases, totals | explicitly justified | Required bookkeeping for eight added map payloads. |
| GOPool | New row | known identity | Twin folded loader hash, capacity 1. |
| GOPool container | Count, tail pointers, chunk size | explicitly justified | Required bookkeeping for one new row. |
| Map marker `+0x00` | Marker UID | known identity | New marker identity. |
| Map marker `+0x08` | Icon-name pointer | known local reference | Points at Twin loader name. |
| Map marker `+0x20` | Flag-array pointer | known local reference | Rebased pointer to unchanged Raven flags. |
| Map marker container | Array pointer/count, copied-row pointer rebases, relocation data | explicitly justified | Required append-only DCB array construction. |
| Coordinate `+0x00` | Marker UID | known identity | Joins Twin marker to Twin coordinate. |
| Coordinate `+0x08` | WAD-name pointer | known local reference | Rebased pointer to unchanged Raven WAD name. |
| Coordinate `+0x10..+0x15` | Position | marker position | Deliberate 32 m east offset so both icons can be observed. |
| Coordinate container | Array pointer/count, copied-row pointer rebases, relocation data | explicitly justified | Required append-only DCB array construction. |

No other payload byte changes are accepted by the builder. Any unclassified byte aborts the build.

The original marker and coordinate arrays remain physically present at their original offsets. Every original record, including both Raven records, is byte-identical there. The active copied arrays are semantically identical; only their relative-pointer fields are rebased. Removing the appended arrays and restoring the original array pointer/count and relocation set reconstructs each frozen DCB byte-for-byte.

## Opaque-field policy correction

`collectible_framework.py` now separates proven identities from opaque donor fields.

Proven identities remain collision-checked and unique: names, folded loader hashes, marker/export UIDs, and WAD record IDs used by references.

Opaque donor fields are not uniqueness-checked. Material `+0x10`, material `+0x20`, other unexplained material scalars, ModelGroup payload fields, and other unexplained payload scalars must remain byte-identical to the proven Raven donor. Both framework test clones now inherit Raven material `+0x10 = 1B0989158D4A2908` and `+0x20 = D595197B0961F689`.

## Offline proof

Builder: `tools/v0.10.4/build-raven-twin-stage-a-offline.py`

Proof: `archive/field-logs/completionist-v104-raven-twin-stage-a-offline.json`

Candidate hashes:

| File | SHA-256 |
|---|---|
| `r_ui.wad` | `86ba2b6a96d869c25f825e5cd64aebae10649d5904f93b5723d53359ed24d0a5` |
| `wad_r_ui.dcb` | `f0f67e7797456c17d2d8c1671c5998668cf48d1ad3a30d15c540363b4df756ae` |
| `mapmaster.dcb` | `2acc035529b7078e73957668e987df24775d464a41fc32f9a0622f26786011bf` |
| `mapcoords.dcb` | `36bd16f8f21c6387b556e156055ea02f5c262b30a6c450cc0efa05734efb1a0c` |

Each file has a structural inverse that returns exactly to its frozen Raven SHA-256. Original Raven records remain byte-identical. Stock Dock/BoatDock records remain byte-identical. Candidate source files are hash-checked before and after the offline build.

## Stage B design only

Stage B is not implemented. After Stage A runtime success is archived, Stage B may replace only the Twin diffuse/emissive resident pixel payloads and matching external texpack stream bytes under the same Twin texture identities. WAD topology, names, IDs, references, marker data, GOPool data, and native map topology must remain byte-identical to Stage A.

## Runtime gate

Use the transactional installer only for a separate, explicit human runtime test. The installer must not launch God of War and must not modify saves, progression, or marker state. Test only map open with original Raven plus Raven Twin. Do not begin Stage B without archived Stage A runtime success.

Offline candidate/report writes reject linked or multi-hardlink destinations and use same-directory atomic replacement. The runtime wrapper pins the exact hardened `036628c` transaction engine SHA-256. Normal rollback can recover persisted `backup-complete`, `installing`, and rollback-in-progress states after abrupt interruption, but still uses `-Force $false` and rejects bytes that match neither the recorded baseline nor approved candidate.
