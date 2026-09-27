# Collected marker state coverage

Updated 2026-09-27. Completion package installed; live transport and map startup checked.
Per-family collection/save-switch evidence remains incomplete.

## Coverage

Contract retains 410 location IDs and excludes 27 repeatable trial rewards.
Loaded reader has 413 exact source paths for 410 IDs; three extra paths cover
level variants. Missing or ambiguous owner stays `unknown`, so pin stays visible.

| Family | Pins | Saved identities | Saved bindings still missing |
|---|---:|---:|---:|
| Legendary chest | 37 | 33 | 4 |
| Wooden chest | 99 | 0 | 99 |
| Coffin | 109 | 0 | 109 |
| Cipher chest | 14 | 0 | 14 |
| Artefact | 45 | 0 | 45 |
| Lore marker | 43 | 0 | 43 |
| Lore scroll | 5 | 0 | 5 |
| Realm tear | 21 | 0 | 21 |
| Treasure dig | 12 | 0 | 12 |
| Treasure map | 12 | 0 | 12 |
| Jotnar shrine | 13 | 0 | 13 |
| **Total** | **410** | **33** | **377** |

Saved identity count means exact object binding plus stock predicate and archived
decoder evidence. It does not mean current game state known or live test passed.
Native replay run on 2026-09-27 returns 23 collected, 9 remaining, 378 unknown.
One of 33 bound chests lacks state in that archived save. These counts belong to
fixture, not user's current save.

All families have loaded-object read paths. These can hide exact loaded objects
and retain accepted collection within same save epoch. After save switch, an
unloaded object with no saved binding stays unknown until exact live state read.
Thus full all-marker saved-state goal still has 377 binding gaps.

## Terminal predicates

Stock sources live under local sibling `completionist-map-gow2018/dist/gowlua-src`.
Generated probes append to pinned scripts and keep stock callback arguments,
returns and errors. New code only reads gameplay state.

| Adapter | Exact read |
|---|---|
| Chest | `interact_chest_standard.lua`: numeric `state == 4` (`OPENED`) |
| Artefact | `interact_loot_artifact.lua`: numeric `state == 3` (`ACQUIRED`) |
| Lore marker | `langcheckruneread.lua`: boolean `mapSummaryComplete` |
| Map / scroll pickup | `sonlanguagepickup.lua`: boolean `collected` |
| Dig | `interact_loot_dirtdig.lua`: `state == 3` plus exact `questName` Complete |
| Rift | `interact_loot_pocketrift.lua`: boolean `hasOpened` after loot finish |
| Shrine | `interact_triptych.lua`: `triptychCompleted` plus exact journal wallet resource |

Dig state and shrine flag can change when interaction starts. Extra quest or
journal check prevents premature hiding. Rift combat finish alone does not
set completion. Treasure map and paired dig use separate catalogue IDs/owners.

Lua 5.1 and 5.2 tests execute the seven stock scripts with probes appended. Engine
stand-ins supply external APIs. These tests prove predicate and wrapper behavior;
each family still needs paired live object-lookup and collection proof.

## Exact ownership and saved data

Loaded lookup requires one matching ancestry, exact placement owner and matching
adapter tag. Duplicate matches stay unknown. Dirty hooks carry level name only;
reader fetches current object state instead of trusting event payload as state.

Saved bindings come from `catalogue/legendary-chest-authority.json`. Native
generator checks ordered contract, serialized keys and duplicate native owners.
Bridge keeps native chest enum separate from normalized wire codes:
`0=unknown`, `1=remaining`, `2=collected`. Invalid or absent records cannot hide pin.

Further chest bindings need exact script carrier GUID and composite owner path,
registry/object hashes, and exact-class replay evidence. Placement record alone
does not prove saved owner. Other families also need matching saved field decoder.
Do not promote catalogue leads just to raise coverage count.

## Remaining live evidence

For each enabled adapter, record exact ID and state before/after collection,
tracked target with map closed, map reopen/filter cycle, checkpoint reload with
source area unloaded, older save, and return to completed save. Check map/dig
independence, Nornir parent/children, reused Niflheim rifts and fast travel.

Native capacities remain 2,048 marker slots, 4,096 query slots and 2,048 UI
physics slots. Native capacity test passed on 2026-09-27. The current Legendary-filter live check used 235 UI bodies out of 2,048, with
300 query entities and 922 registry entries. This is not a full stress test.

## Current live delivery

The 2026-09-27 timing-fixed package reports `reader_enabled=true`,
`timer_enabled=true`, and `clock=ui_elapsed`. At 15:50:51 the Lua store accepted
31 collected and two remaining Legendary states after a restore boundary.
An independent native query agrees. The 377 unknown states remain visible.
Midgard has 23 collected, two remaining and three unknown Legendary locations;
Alfheim has five collected, and Helheim three collected plus one unknown.
The user confirmed that only the expected few Midgard Legendary pins remain.

The prior timestamp reader repeatedly expired responses because GoW uses Lua
5.2 with four-byte numbers, as shown by the extracted stock bytecode header.
The UI-delta clock avoids that precision loss. Regression tests drive a complete
410-state response across the bounded receive loop into the generated map store.

The 09:50 crash screenshot and `GoW.exe.65176.dmp` both identify an unavailable
`getfenv` call in the appended lore adapter. All adapters now use direct callback
wrappers and preserve stock arguments, return values and original errors.
