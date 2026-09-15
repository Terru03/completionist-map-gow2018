# Raven read-only registry differential — 2026-09-15

## Result

The debugger path is incompatible with the supported GoW build/runtime: attaching with `DebugActiveProcess` succeeds and breakpoints install, but GoW exits before any target event. The safe read-only registry path works and does not terminate the game.

Current status remains fail-closed:

- `BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY`
- `BLOCKED_EXACT_UNLOADED_STATE_ORACLE`

Archive:

`archive/field-logs/runtime-captures/gow-raven-readonly-all-registries-20260915-204839`

Commit:

`dc75c4648d289cc5cbc158bd17795c9dcb41efd3`

## Safety / capture mode

The successful all-registry probe used only:

- `PROCESS_QUERY_INFORMATION`
- `PROCESS_VM_READ`

It did not use:

- debugger attachment
- breakpoints
- process writes
- thread suspend/resume
- save writes
- progression writes

## Main-menu baseline

The fully loaded main menu had 12 live registry-table entries and 46 validated GameObjects.

Active registries with validated objects:

| registry ID | validated objects | cursor | live count |
| ---: | ---: | ---: | ---: |
| 0 | 23 | 24 | 24 |
| 1 | 9 | 10 | 10 |
| 18 | 11 | 12 | 11 |
| 24 | 3 | 4 | 3 |

The between-runs main-menu snapshot returned to the same active-object pattern: registries `0`, `1`, `18`, and `24`, total 46 validated objects.

## Run A — standing near the canonical Raven

The target save/area produced 14 live registry-table entries and 109 validated GameObjects.

Active registries with validated objects:

| registry ID | validated objects | cursor | live count |
| ---: | ---: | ---: | ---: |
| 0 | 36 | 499 | 37 |
| 1 | 9 | 19 | 10 |
| 238 | 54 | 55 | 54 |
| 241 | 10 | 11 | 10 |

The main-menu registries `18` and `24` were no longer active. Two new active registries appeared: `238` and `241`.

## Run B — same save, same Raven after reload

The second load produced 14 live registry-table entries and 113 validated GameObjects.

Active registries with validated objects:

| registry ID | validated objects | cursor | live count |
| ---: | ---: | ---: | ---: |
| 0 | 40 | 946 | 41 |
| 1 | 9 | 19 | 10 |
| 238 | 54 | 55 | 54 |
| 241 | 10 | 18 | 10 |

Again, the area-specific active registries were exactly `238` and `241`.

## Strong runtime differential

Across both reloads:

- registry `238` is present only in the target loaded context and contains exactly 54 validated GameObjects;
- registry `238` has cursor `55` and live count `54` in both Run A and Run B;
- registry `241` is present only in the target loaded context and contains exactly 10 validated GameObjects;
- registry `241` has live count `10` in both runs, but its cursor moves from `11` to `18`;
- returning to the main menu removes both `238` and `241` from the active-object set and restores the 46-object baseline pattern.

This is the strongest runtime narrowing so far. The canonical Raven's WAD/object is therefore expected to belong to the target-area-specific runtime state represented by registry `238` or `241`, but exact WAD-to-registry binding is not yet proved.

Registry `238` is notably more deterministic at the observed aggregate level than `241`: its object count, cursor, and live count are identical across both reloads. This is supporting evidence only; it is not sufficient to claim that `238` is `alf355_chiseldungeon.wad` or that any particular slot is the Raven.

## Negative candidate result

The all-registry object traversal itself is working: it validated 109 GameObjects in Run A and 113 in Run B. However, no object scored against the current canonical Raven evidence within the probe's shallow pointer graph:

- exact canonical payload
- Raven GUID ASCII
- `goprecisionchallenge_raven_perch`
- `ravenKilled`
- final record ID
- override record ID
- prototype ID
- canonical world-position components

Therefore `candidate_count=0` does **not** mean the Raven object is absent. It means those catalogue identifiers are not directly reachable in the first two pointer hops / bounded blobs used by this probe.

## Scheduler-root diagnostic

The read-only scheduler traversal reported `scheduler_outer_count=0` in all snapshots. Since the registry table clearly changes correctly with save/area load, the current `SCHEDULER_OUTER_SENTINEL_RVA` interpretation is considered untrusted and must not be used to infer absence of scheduler state.

## Precise remaining edge

The remaining live edge is now narrower:

```text
area-specific registries {238, 241}
        ↓
prove which registry is alf355_chiseldungeon.wad
        ↓
identify the exact canonical Raven GameObject within that registry
        ↓
(registry_id, flavor, slot)
        ↓
persisted GameObject token
        ↓
frozen-save savedInfo.ravenKilled binding
```

Do not promote runtime generation. Unknown completion state remains hidden/no marker.
