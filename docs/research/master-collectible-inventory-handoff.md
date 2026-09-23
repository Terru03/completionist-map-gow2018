# Master inventory handoff — 2026-09-23

Branch: `codex/master-collectible-inventory`.
Latest full run: `archive/field-logs/master-inventory/master-collectible-inventory-20260923-122418` (commit `5ff9841`). The run pins seven source files by branch commit and SHA-256. Its archived files match all seven hashes. Game stayed closed. No game or save file was written.

## Verified result

| Family | Physical | Native target | Tracked candidates | Explained untracked | Unresolved |
| --- | ---: | ---: | ---: | ---: | ---: |
| Odin's Raven | 53 | 51 | unknown per object | 0 | 2 aggregate surplus |
| Nornir Chest | 22 | unknown | 21 | 1 | 0 |
| Legendary Chest | 64 | unknown | 33 | 29 (27 trial, 2 non-map) | 2 |

Raven native audit narrows surplus to two parent groups: CalderaShores has 2 physical / 1 target; Riverpass has 7 / 6. It does not name the bonus object in either group. All nine rows in those groups carry that open membership status. All 53 physical rows stay in inventory.

Legendary guide count is 34; native tracked candidates are 33. Keep gap visible. The 33 candidates are not a production allowlist. All 293 inventory rows keep `mod_marker_allowed=false` and `marker_generation_ready=false`.

## Tests and sources

Master wrapper ran 17 unit tests and built report from pinned files. Source manifest pins Raven `f665f61`, Legendary `e14bef3`, Nornir `37f19b1`, and Ship Head seed `36bf343`. Legendary gate ran 10 tests plus 12 identity tests. Nornir gate ran 7 tests. Both gates still say `BLOCKED_FAIL_CLOSED`.

## Open work

- Raven: find exact bonus object in each surplus group from native evidence. Do not assign by count alone.
- Legendary: prove direct chest-to-RegionSummary ownership for 33 candidates, settle two unresolved physical rows, and prove custom marker/map/world path. Pinned asset scan found no Legendary/Chest-named class in 382 mapmaster rows or 119 `r_ui.wad` mapicon names. This is a class-name negative check only.
- Nornir: prove direct ownership and persistent unloaded OPENED state for 21 candidates. Keep Helheim triple-chest reward as physical explained untracked row.
- Other families: build branch-local gates for Artefact and Lore rows. Master seed rows stay unclassified until native family evidence exists.

Next safe step: trace an exact Legendary chest-to-region edge from shipped data, or add an Artefact/Lore static gate on its own branch. Keep game closed and gate blocked until proof is exact.
