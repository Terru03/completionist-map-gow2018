# Hide collected map markers

## Request

> now that we have all markers on the map, start a plan that removes markers from the map if their state is "collected"

Scope: completion behavior for the current God of War map build. Cover current 551
collectible definitions: 410 location pins, 53 Ravens, 22 Nornir chests, and 66
Nornir children. Counts describe definitions; realm, filter, and puzzle rules
still decide which pins show.

## Current evidence

Updated 2026-09-27. The completion runtime, seven stock-script adapters, native
transport, package builder and reversible installer are implemented. Installed
operation is `7d93a92c6f474c4aa72bacd95d9ff94b`. See the
[build record](../../builds/v0.10.5-hide-collected.md) and
[coverage table](../../research/collectible-state-coverage.md).

All 410 IDs have exact loaded-object paths. Native saved-state decoding covers
33 Legendary identities; the other 377 IDs still lack saved bindings. The live
save returns 31 collected and two remaining, and the Lua state store now receives
those values. Unknown locations remain visible. Full unloaded-save acceptance
in requirement 1 therefore remains incomplete for the unbound objects.

The initial live package crashed because its callback wrapper used `getfenv`.
The replacement uses direct wrappers. A second live issue was clock precision:
GoW bytecode declares Lua 5.2 and four-byte numbers, so absolute Unix time cannot
represent short polling intervals. The reader now uses UI elapsed time and the
regression tests exercise a full 410-state response through the generated map.

The current code passes 160 collectible checks and 50 Raven/Nornir checks. Native
bridge/capacity checks, full Lua compilation, deterministic package composition,
actual DLL contract checks and exact rollback checks also pass. Per-family live
collection and save-switch evidence is still required for full coverage claims.

## Required behavior

1. Accepted exact state `collected` removes that object's pin in All,
   Completionist, and its family filter. Already-collected objects disappear
   after current save state arrives, including objects in unloaded areas.
2. Live collection removes pin at next UI sync. If map closed, next open omits
   pin. A selected collected pin loses reticle/footer action. Its own tracked
   compass target clears, including when collection occurs with map closed.
3. Fresh or older save restores pins for objects uncollected in that save.
   State from prior save, process, or restore epoch cannot hide current pins.
4. Duplicate collection events have no extra effect. Delayed snapshots cannot
   revive an object collected later in same save epoch. Within one epoch,
   unknown means no new evidence; it preserves an accepted remaining/collected
   observation. A real restore boundary resets prior state to unknown.
5. Nornir chest completion removes parent and all linked children. Broken seal
   removes only its own pin. Bell hits and mechanism positions do not count as
   permanent collection. Existing locked-attempt child reveal still applies.
6. Treasure map pickup and treasure dig completion remain distinct states.
   Collecting map does not mark paired dig collected.
7. Per-object state comes from exact native identity and proved game state.
   Missing actor, unloaded WAD, failed read, missing record, discovery, region
   total, and nearby collected object cannot count as collection.
8. Default for new 410-location layer: `unknown` stays visible subject to current
   realm/filter rules. Only proved `collected` hides it.
   Raven authority and Nornir child rules keep their existing stricter checks.
9. Instantiate one state store before the map layer loads and drive its epoch
   from the existing verified save lifecycle. The complete generated artifact
   must work without test-only global injection or manual epoch advances.

## Constraints

- Game: God of War (2018), Steam Build ID `11168363`; runtime Lua `5.2` with four-byte numbers (verified bytecode header).
- Loader: GoW Script Loader & Gameplay Tweaks `0.22`; native build Windows x64,
  MSVC, C++20, CMake `3.24` or newer. Python test commands use `py -3.14 -B`.
- Read gameplay/save state only. Change UI state; do not set quest progress,
  completion flags, counters, inventory, or write saves.
- Keep existing marker identities, placements, category filters, artwork,
  native compass Add/Replace/Remove behavior, and one active target.
- Keep 2,048 marker-radius slots, 4,096 map query slots, and 2,048 UI physics
  body/shape slots for world 7. Preserve current enlarged icon pool.
- Keep three reused Niflheim rift IDs owned by location layer on normal map;
  native fast-travel behavior stays intact.
- Keep 27 repeatable trial rewards excluded. Current fixed unresolved locations
  remain in catalogue; exact collection proof decides hiding.
- Build from verified current recovery package. Rollback of new change must
  restore this working package, not pre-recovery files with map-open crashes.
- Preserve existing unrelated and uncommitted work. Keep raw game data and
  generated binaries local per repository policy.

## Acceptance evidence

Require Lua tests for state transitions and actual composed map behavior,
native decoder/transport tests for any changed bridge, deterministic offline
package checks, and live paired collected/uncollected proof per enabled adapter.
Each live proof needs current-save identity, object ID, before/after state, map
result, checkpoint/reload, and switch-to-other-save result. Mark missing evidence
as unresolved; do not claim full state coverage from marker count alone.
