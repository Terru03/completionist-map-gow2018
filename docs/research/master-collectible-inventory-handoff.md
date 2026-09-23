# Master inventory handoff — 2026-09-23

Branch: `codex/master-collectible-inventory`. Latest full archived run: `archive/field-logs/master-inventory/master-collectible-inventory-20260923-125425` (commit `665429d`). The run pins 11 source files by branch commit and SHA-256, runs 19 master tests, and builds 293 physical rows. God of War stayed closed. All 293 rows have `mod_marker_allowed=false` and `marker_generation_ready=false`.

| Family | Physical | Native target | Direct/tracked evidence | Open |
| --- | ---: | ---: | ---: | ---: |
| Odin's Raven | 53 | 51 Labor | exact two surplus IDs unknown | 9 objects in two groups |
| Nornir Chest | 22 | 21 candidate | 21 tracked candidate, 1 Helheim explained untracked | ownership/state |
| Legendary Chest | 64 | 33 candidates | 33 candidate, 27 trial, 2 non-map | 2 class unknown; ownership/state |
| Artefact | 45 | 10 Ship Head target only | 9 Ship Head direct parents | 36 other accounting; Ship Head 9/10 |
| Lore Marker | 43 | 43 Summary | 40 direct object parents | 3 level script object links |

Raven surplus groups stay CalderaShores 2 physical / 1 target and Riverpass 7 / 6. Legendary guide 34 remains distinct from native candidate 33. Lore guide 39 remains distinct from native target 43. No row was removed to fit either guide count.

Artefact gate on `codex/collectible-artefacts` removed two false cross-subtype Ship Head parent assignments from a Toy and Mask. Lore gate on `codex/collectible-lore-markers` proved 40 direct object parent attributes. Three compiled level Lua blobs have journal and Summary callback clues, but no exact callback-to-object link; their catalogue parent fields stay null. Neither family has proved unloaded persistent state or marker delivery.

Open static work: exact Raven surplus IDs; Legendary/Nornir ownership and persistent states; three Lore level-script object links; non-Ship-Head Artefact accounting; native marker/resource audits. Start branch-local gates for remaining families. Keep all runtime generation blocked until exact evidence closes each gate.
