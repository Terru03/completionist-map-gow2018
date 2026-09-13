# All-Ravens v0.10.5 WIP review — 2026-09-13

This review was performed against `codex/all-ravens-release-candidate` after the
`WIP: build all-Ravens release candidate` commit. It is an offline review only.
No game files, saves, or progression were written and no runtime-pass claim is
made here.

## Branch/base integrity

The WIP branch is directly based on the human-runtime-proven v3.3 capture commit
`fcee0241f4258b0195c2b54eae6f18a2b4d2b367` and is two commits ahead of that
base. This is the correct ancestry for generalising the proven Raven behavior.

## 53 native Ravens vs 51 labor target

Keep all **53** native Raven instances in the completionist catalogue and in the
production marker set. The native `quests.dcb` parent target counts sum to 51,
but the static WAD extraction finds 53 killable Raven instances. Community PC
references independently corroborate that God of War contains 53 Ravens while
only 51 are required for the labor/achievement, with one extra in River Pass and
one around Ruins of the Ancient / Shores of Nine.

Therefore the object/target surplus must not be interpreted as two cut or fake
Ravens. The current label `parent_has_one_hidden_surplus_raven` is misleading.
Use neutral metadata such as `parent_contains_one_bonus_untracked_raven` until
row-level bonus identity is proven from native/runtime evidence.

The Caldera Shores extra is strongly associated with the `xpl930_beachruins.wad`
row (Ruins of the Ancient), but this is not yet accepted as native row-level proof.
River Pass has seven physical rows versus a parent target of six; exact bonus-row
identity is likewise metadata-only and does not need to gate marker generation,
because all seven physical Ravens belong in a completionist map.

## Runtime regression found: hiding a custom Raven by raw ID

The generalized `all-ravens-map-runtime.lua` currently does this in
`hideCustom`:

```lua
local ids, ok, err = customIds()
...
game.Compass.HideMarker(id)
```

That is a behavioral drift from the human-runtime-proven v3.3 router. In actual
runtime, `FindMarkersByIconClass({"CompletionistRaven"})` returned numeric/native
marker IDs. Proven v3.3 resolves a known custom ID back to its Completionist
marker **name** and calls `HideMarker(name)`, with the raw ID only as a fallback.

Before any v0.10.5 runtime test, generalize v3.3's `knownNameForId` behavior to all
catalogue rows:

1. Build/maintain a lookup from exact marker ID string to catalogue row/name.
2. For each custom Raven ID returned by `FindMarkersByIconClass`, resolve the
   exact known Completionist marker name.
3. Hide by the known marker name.
4. Only use the raw ID as fail-safe fallback when no exact catalogue name can be
   resolved.
5. Preserve fail-closed replacement: do not show a new Raven after a required
   old-target hide failed.

This matters both for Raven -> Raven replacement and for custom Raven -> stock or
Nornir/native replacement.

## Test-harness gap that currently masks that regression

`test_all_ravens_lua.py` currently makes the fake Compass store marker names in
`customIds`, and `game.Map.GetMarkerInfo(name)` returns `{Id=name}`. That does not
model the runtime API we observed.

Change the mock so:

- every marker name maps to a deterministic numeric/native-like ID;
- `GetMarkerInfo(name).Id` returns that ID;
- `ShowMarker(name, class)` records the numeric ID as active;
- `FindMarkersByIconClass` returns numeric IDs;
- the mock can distinguish `HideMarker(known_name)` from
  `HideMarker(raw_numeric_id)` for custom Ravens, so a regression back to the raw
  ID path fails the test.

Re-run A -> B, B -> A, same-marker second-click removal, Raven -> stock,
stock -> Raven, Raven -> Nornir, tracked-Raven kill, and teardown using that
runtime-faithful mock.

## Selection-state regression coverage to add

The generalized Lua correctly avoids treating an incidental noncustom collision
callback as proof of a real selection change, matching the v3.3 lesson. The pure
Python model currently clears selection immediately on a noncustom collision,
so it does not cover the failure mode that previously broke Twin routing.

Add direct Lua and/or model coverage for:

1. exact Raven collision -> candidate;
2. one or more incidental noncustom collision callbacks;
3. arbitrary human delay / no frame TTL;
4. matching exact Raven prompt UID -> arm;
5. matching exact action -> consume/show;
6. a genuinely different stock/native UID -> disarm and delegate native;
7. stale Raven state must never hijack that stock action.

## Loaded-instance matcher review

The gameplay event adapter identifies a loaded Raven by exact parent quest plus
static world position and accepts only squared distance `<= 0.25` (0.5-unit
radius). The extracted same-parent Raven positions are separated by many game
units, so the current radius is conservative; do not widen it without a new
ambiguity audit.

The adapter remains read-only: it publishes the Raven object's own
`ravenKilled` Boolean and performs no quest/save/progression write.

## State gate remains the real release blocker

The current fail-closed policy is correct: unknown per-Raven state means no map
marker. The loaded-instance `OnStart`/restore/hit bridge cannot initialize Ravens
whose WADs are unloaded, especially Ravens killed before mod installation.

Do not replace this with region counts, actor absence, or `currMarkerID`
inference. Those are not exact per-instance state.

The next state task should stay narrowly scoped to a **read-only** oracle for one
known unloaded instance first. Use the proven Veithurgard identity:

- catalogue ID: `raven_642d0d164af0a5d4076e77933c549a5d`
- instance GUID: `642d0d16-4af0-a5d4-076e-77933c549a5d`
- parent: `RegionSummary_VF_Raven_Parent`
- WAD: `xpl200_funeral.wad`
- marker: `Completionist_V103_Veithurgard_Raven_01`

A future diagnostic should compare that same native instance across the backed-up
fresh/uncollected and progressed/collected saves before visiting/loading its
region, without writing game/save/progression state.

## Resume checklist for the next Codex window

1. Preserve all 53 physical Raven rows/markers; do **not** reduce production to 51.
2. Rename misleading surplus metadata; treat 51 as labor/region-target accounting,
   not physical collectible count.
3. Port v3.3's name-resolved custom-target hide semantics to the N-Raven router.
4. Make the Lua Compass mock return numeric IDs and prove the name-resolved hide
   contract.
5. Add incidental-collision + delayed-human + genuine-stock-disarm regressions.
6. Rebuild deterministic candidate/proof and rerun broad suites and transaction
   self-test.
7. Keep `ready_for_runtime_test=false` while unloaded per-instance state is
   unresolved.
8. Investigate only a read-only unloaded-state oracle next; no game install,
   launch, save mutation, progression mutation, or `main` merge yet.
