# Master inventory handoff — 2026-09-23

Branch: `codex/master-collectible-inventory`.

Latest full archived run before this handoff update: `archive/field-logs/master-inventory/master-collectible-inventory-20260923-131754` at remote commit `ed77a95a4eb56072683df975b3d6a12aefc58346`.

God of War stayed closed throughout this pass. No game process was opened, no runtime build was installed, and no game/save files were written.

## Verified master result

The latest run builds **293 physical rows** from pinned family evidence. Every row remains fail-closed:

- `mod_marker_allowed=false`
- `marker_generation_ready=false`
- production-ready count = 0 for every family

| Family | Physical | Native target / candidate evidence | Direct/tracked evidence | Open proof gaps |
| --- | ---: | --- | --- | --- |
| Odin's Raven | 53 | 51 Labor target | aggregate surplus narrowed to two groups | exact two surplus object IDs; persistent unloaded state remains family concern |
| Artefact | 45 | 10 Ship Head target only | 9 Ship Heads have direct parent attributes | 36 other accounting joins; Ship Head 9/10; unloaded state; marker path |
| Nornir Chest | 22 | 21 tracked candidates | 21 candidate + 1 Helheim explained untracked | exact ownership and persistent unloaded `OPENED`; marker path |
| Legendary Chest | 64 | 33 tracked candidates | 33 candidate, 27 trial, 2 non-map | 2 class-unknown rows; 0/33 direct ownership; one staged-state gap; marker path |
| Lore Marker | 43 | 43 native Summary target | 40 exact object parent names | 3 level-script callback-to-object links; unloaded state; marker path |
| Realm Tear Encounter | 0 master rows | 19 native PocketRift Summary targets | 14 direct callback carriers in source evidence | exhaustive physical encounter census and per-object membership |
| Jotnar Shrine | 0 master rows | native Triptych objective target = 11 | 13 distinct named physical placements observed by research gate | exhaustive physical census and exact 11/13 membership |
| Purple Language Cipher Chest | 0 master rows | two native four-piece language quests = 8 pieces | cipher names found in shared script path, no exact placed chest item record | physical chest census and exact per-chest reward identity |

External guide counts remain audit-only and are not used to create, delete, or promote native rows. Notable visible disagreements remain:

- Legendary guide = 34 vs native tracked candidates = 33.
- Lore guide = 39 vs native Summary target = 43.
- Cipher guide = 13 chests vs native quest accounting = 8 language pieces.

## Pinned family branches / remote HEADs

- Master inventory: `codex/master-collectible-inventory` — latest archived-run HEAD `ed77a95a4eb56072683df975b3d6a12aefc58346` before this documentation commit.
- Ravens: `codex/all-ravens-release-candidate` — pinned by master at `f665f61935e1723c2b68d1e162cbde228e7de89b`.
- Nornir: `codex/collectible-nornir-chests` — `37f19b164bf370578ed058274d5020c2d5ab02ad`.
- Legendary: `codex/collectible-legendary-chests` — `e14bef3f09f17f3f10f2e12b95640d7417b8cdc5`.
- Artefacts: `codex/collectible-artefacts` — `061f5131a11ab7d61c24900e3a1324d1c899602e`.
- Lore Markers: `codex/collectible-lore-markers` — `740e06afe90cee7839919d806eed8c17647e3970`.
- Realm Tears: `codex/collectible-realm-tears` — `4dbecd9b6c5939810608a6b4401965ca771ff6d8`.
- Jotnar Shrines: `codex/collectible-jotnar-shrines` — `3f2b215eb04618619afa53dc1bf8b1a127fb3698`.
- Cipher Chests: `codex/collectible-cipher-chests` — `472a8ce20b08286689e48a4fb65fc7c23c120fff`.
- Ship Head seed: `codex/collectible-ship-heads` — pinned by master at `36bf3438b5453b556ddcbb45637a6c6b939d3252`.

## Work completed in the latest offline pass

### Artefacts

Branch-local static gate and tests were added. A catalogue bug was corrected: a Toy and a Mask had inherited Ship Head parent assignments through region inference even though their exact WAD overrides did not contain those parent names. Those unproved assignments were removed while preserving all 45 physical Artefact rows.

Current Artefact evidence:

- 45 physical Artefacts preserved.
- 9 Ship Heads have direct parent attributes.
- Ship Head native target remains 10.
- remaining 36 Artefacts are accounting-unresolved.
- unloaded persistent state and marker delivery remain blocked.

### Lore Markers

Branch-local static gate and tests were added.

- 43 physical Lore rows preserved.
- native Summary target = 43.
- 40 rows have exact parent names in their object records.
- three level Lua blobs contain journal / quest / read clues, but there is no exact callback-to-physical-object edge for those three.
- their catalogue parent fields remain unpromoted.

### Realm Tears

A branch-local offline research gate was added.

- native object terminology uses `PocketRift`.
- quest data exposes 19 Summary targets.
- 14 direct callback carriers were found in placed override records.
- this is not yet an exhaustive physical encounter census, so no Realm Tear physical rows were added to master.

### Jotnar Shrines

A branch-local offline research gate was added.

- native data uses `triptych`.
- native objective target = 11.
- research found 13 distinct named physical placements after removing one exact duplicate across WADs.
- eleven placement WADs contain the `interact_triptych` quest script; two Tyr placements do not.
- exact 11/13 membership remains unresolved, so no Jotnar physical rows were promoted into master.

### Cipher Chests

A branch-local offline research gate was added.

- native quest data contains two language goals with four pieces each (8 pieces total).
- the common `interact_chest_standard` script names both cipher pieces.
- scanned placed chest records did not provide an exact per-chest cipher item binding.
- physical cipher chest census remains unproved, so master contains no Cipher physical rows.

## Legendary resume point

The Codex pass returned to Legendary immediately before the usage limit was hit. The intended focused work was:

1. recheck all existing frozen captures for the one missing `xpl100_httk` staged state;
2. search `stn200_lakeext.wad` and `xpl300_stronghold.wad` for exact positive native class evidence;
3. continue exact chest-to-RegionSummary ownership tracing.

The earlier check established that existing frozen staged reports contain **no `xpl100_httk` carrier**, so those captures cannot prove its staged state. Keep that state gap blocked unless another frozen/static source supplies positive evidence.

No new Legendary commit was pushed after `e14bef3`. Therefore do **not** assume any terminal-only Legendary findings after that commit were preserved.

Current Legendary invariants remain:

- 64 physical rows;
- classes: 33 tracked, 27 trial reward, 2 non-map-counted physical, 2 unresolved;
- direct ownership bindings = 0/33;
- one tracked candidate lacks an observed exact staged state in the accepted frozen capture;
- custom/native marker path remains unproved;
- static gate remains `BLOCKED_FAIL_CLOSED`.

## Other high-value open static work

- Raven: identify the exact surplus object in CalderaShores (2 physical / 1 target) and Riverpass (7 / 6) from positive native evidence; never choose by order/count alone.
- Nornir: prove exact ownership and persistent unloaded `OPENED` state for the 21 tracked candidates; keep Helheim triple-chest as physical explained-untracked.
- Artefacts: resolve non-Ship-Head accounting and Ship Head 9/10 gap; then persistent state and marker path.
- Lore: close the three script callback-to-object joins, then persistent state and marker path.
- Realm Tear / Jotnar / Cipher: convert research gates into exact physical catalogues only when positive native identity and membership evidence exists.
- Remaining families still need isolated gates: Treasure Maps, Treasure Dig Spots, Hidden Chambers, Valkyries / Queen, Dragons, Favors, Mystic Gateways, Shops.

## Operating rules for the next pass

- Keep God of War closed until static/offline work is exhausted.
- Keep family branches isolated.
- Preserve physical rows even when external/native accounting counts differ.
- Never use guide counts as join authority.
- Never promote inferred ownership to exact proof.
- Keep runtime generation fail-closed until family-specific identity, persistent completion state, marker-resource path, and suppression semantics are proved.
- Archive meaningful negative and positive evidence in Git, commit frequently, and push every branch before switching tasks.

Best next action: resume the interrupted Legendary static investigation from `e14bef3`; if exact ownership/classification remains blocked, continue with the remaining branch-local family gates rather than spending the whole session on one edge.
