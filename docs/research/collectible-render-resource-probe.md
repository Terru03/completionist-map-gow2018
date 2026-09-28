# Collectible artwork: private rendering resources, two-family test

Status, 2026-09-28: **installed; visual coexistence not yet verified**.

The user wants one custom icon per collectible type, using the supplied PNGs.
The previous 15-family package rendered every new type as Wooden Chest and was
rolled back. Do not reinstall that package or describe its structural tests as
proof that different artwork renders correctly.

## Current installation

- Builder: `tools/v0.10.5/build-collectible-render-probe.py`.
- Output: `build/collectible-family-art/render-probe`.
- Package: `19af9bef15a84549dd3c4d1180b3822fd2be95e8b19179f4883f955063d48962`.
- Operation: `805262c5c5a8406e8d46831a0150b771`.
- Candidate WAD SHA-256: `11ba0a7715a364267b623b0c9096ebd26799617357502f4e33b53a826f5db6a8`.
- Baseline WAD SHA-256: `5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60`.

The probe rebinds only 45 Artefacts and 99 Wooden Chests. Other collectible
bindings and all Raven records retain their baseline bytes. The game was closed
for installation. The installer returned successfully and a separate verify
returned `ARTWORK_VERIFY_OK`.

Completion v6 was verified before installation (`VERIFY_OK`). The artwork
package pins 17 preserved files, including all 11 v6 target files, the runic
reader, game executable, loader, coordinates, compass graph and permanent pool.
It does not ship or write any of those files. Selection/filter logic, save reads,
and native capacity fixes are unchanged.

## What the new probe changes

Each new type retains its own GameObject, prototype, model, material, diffuse
texture and emissive texture. It now also owns two distinct rendering resources:

| Type | Private mesh group | Private pixel shader |
| --- | --- | --- |
| Artefact | `MG_cmf_artefact_0` | `cmf_artefact_ps_10000207` |
| Wooden Chest | `MG_cmf_wooden_chest_0` | `cmf_wooden_chest_ps_10000207` |

The new model points to its private mesh group; its material points to its
private pixel shader. Both payloads retain the exact donor bytes. Geometry,
shader bytecode, shader flags, vertex shader and the common stock highlight
materials are preserved. Only resource identities and the relevant dependency
links change.

The material's `+0x20` qword is retained as `D595197B0961F689`. Its precise
semantics are not proved; calling it the map-icon shader key is premature.
The independent `+0x10` material identities from the family builder remain.
This is a combined isolation experiment, not a one-variable causal proof.

The pack contains exactly four textures, compiled from the existing Artefact
and Wooden Chest PNGs. It uses the established 148 x 148, eight-mip resident
layout and matching pack/TOC/GNF user hashes.

The object pool is not enlarged: 144 existing spare entries are reassigned.
No new physics objects or marker locations are created.

## Evidence and corrections to the previous diagnosis

1. The failed package already contained independent GameObjects. Changing only
   their names again would not address the unresolved sharing.
2. Older probes already tried model-group isolation and prototype-child IDs.
   They failed visually; they are not new remedies. The old model-group helper
   also used incorrect type accounting for its map MG clones.
3. Payload type `0x2000C` is **Model**, while `0x1000C` is **Model Group**.
   The failed 15-type package did add 15 models, so its `0x2000C +15` increment
   was appropriate. Its lack of MG clones is a separate issue. Do not infer
   resource types from physical WAD ordinals: resident GPU records are untyped.
4. Stock Fight Location and Primary Quest have different PS resource IDs with
   byte-identical DXBC. Their DXBC SHA-256 is
   `b43f948a23b4346dab218b1a78a67715ee2a80bdbbc067eebfcd12b5db749242`.
   All failed family clones instead referenced Dock/Raven's single PS resource.
   This provides a concrete stock pattern for testing private shader resources;
   it does not prove shader sharing caused the failure.
5. Native inspection of the pinned executable
   (`caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`)
   confirms that the shader resource factory allocates a wrapper per resource
   (`GoW.exe+0x4615CE` onwards, 0xC0 bytes) and initializes its program from
   the serialized DXBC at `+0x4616B3`. Material dependency resolution at
   `+0x4BE710` through `+0x4BE7E8` selects shader-resource wrappers. Cloning
   these resources therefore changes a real runtime boundary, not just labels.
6. The inherited model dword `+0x48 = AE7914B9` was also investigated.
   `+0x55998D` copies it to resource `+0x170`; `+0x55976C` copies it to model
   instance `+0x1B4`. Its downstream semantics are unresolved. This probe
   deliberately preserves it instead of assigning an unproved cache key.

Scratch disassembly and shader dumps are under
`build/collectible-family-art/research`; they are local evidence, not shipped
game modifications. No executable patch was added by this work.

## Binary accounting and validation

The WAD gains 20 payload records, of which 16 are typed. Its type-table deltas
match actual payload tags, preserving any preexisting baseline discrepancy:

| Type | Delta |
| --- | ---: |
| `0xA` Material | 2 |
| `0x1000A` Shader | 2 |
| `0x1000C` Model Group | 2 |
| `0x2000C` Model | 2 |
| `0x10001` Prototype | 2 |
| `0x20001` GameObject | 2 |
| `0x10015` Texture definition | 4 |

Seventeen existing artwork tests and eight probe tests passed. Checks cover
private MG/PS dependency resolution, exact shader/geometry preservation,
correct type accounting, deterministic builds, collision rejection, marker
scope, unchanged pool capacity, and transaction recovery using real files.
The rollback test works even after deleting the candidate package. A simulated
failure after replacing the WAD restores every applied file and preserves v6.

Both compositions must be byte-identical before an immutable package is
created. Source inputs, tools and textures are pinned in the package report.
`runtime_coexistence_verified` remains false until real in-game evidence exists.

```powershell
py -3.14 -B tools/v0.10.5/build-collectible-render-probe.py
py -3.14 -B -m unittest discover -s tools/v0.10.5 -p 'test_collectible*art*.py'
py -3.14 -B -m unittest discover -s tools/v0.10.5 -p test_collectible_render_probe.py
py -3.14 -B tools/v0.10.5/install-collectible-family-art.py verify --output build/collectible-family-art/render-probe --operation build/collectible-family-art/render-probe/backups/805262c5c5a8406e8d46831a0150b771/operation.json
```

## Live acceptance and rollback

On a fresh launch, compare Artefact, Wooden Chest and Raven artwork. Test both
the combined view and category filters; close/reopen the map, then restart the
game and repeat. Verify a stock icon as well. A collected marker being hidden
is expected and does not prove the artwork is missing.

Keep the rollout at these two types until that comparison passes. Do not treat
the package report or shader disassembly as a substitute for visual evidence.

If icons collapse, disappear or crash the map, close the game and run:

```powershell
py -3.14 -B tools/v0.10.5/install-collectible-family-art.py rollback --output build/collectible-family-art/render-probe --operation build/collectible-family-art/render-probe/backups/805262c5c5a8406e8d46831a0150b771/operation.json
py -3.14 -B tools/v0.10.5/install-collectible-completion.py verify --output build/collectible-completion-upgrade-v6 --operation build/collectible-completion-upgrade-v6/backups/6aa7d6f9a2b94fa092b17bdbc65f4398/operation.json
```

Use this artwork operation's backup. Older completion rollback journals restore
older completion versions and are not the recovery path for this test.
