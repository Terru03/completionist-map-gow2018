# All Ravens native catalogue

## Result

Native PC data yields 53 Raven instances in 39 WAD files. Distribution is 45 in
Midgard, 2 in Alfheim, and 6 in Helheim. The catalogue covers 22 native region
summary parents.

The extraction does not inspect live Raven actors. It scans static WAD records,
follows native transform parents, and rebuilds world positions. A collected Raven
therefore stays in the catalogue even when no actor exists in the current save.

## Stable identity

Each row uses the native WAD instance GUID as its static Completionist identity.
It also records the object GUID, override record, parent RegionSummary quest,
source WAD SHA-256, native record offsets, local transform, transform chain, and
native world position. Custom marker names and UIDs are generated from that
identity. The runtime-proven Veithurgard marker keeps its exact v3.3 name, UID,
and authored half-float position.

`mapmaster.dcb` supplies realm and region ownership. `mapcoords.dcb` and
`compassgraph.dcb` supply canonical coordinate-WAD names. `quests.dcb` supplies
parent Raven targets. Those targets sum to 51. Two native instances exceed parent
targets: one in River Pass and one in Caldera Shores. They remain in the 53-row
catalogue because native instances, not achievement targets, define static sites.

## State evidence

`precisionchallenge.lua` owns a local Boolean named `ravenKilled`. Its checkpoint
save callback returns this field. Its restore callback restores this field. Its
weapon-hit callback changes it after a valid Raven hit and then reports challenge
completion to the parent RegionSummary quest.

The candidate state adapter matches a loaded script instance by exact parent quest
and unique native world position. It only reads `ravenKilled`. It never calls a
quest, marker, collectible, save, or progression write API.

Native script and resource searches found no proven API that reads the saved
`ravenKilled` field for an unloaded WAD instance by GUID. Parent RegionSummary
counts are aggregate data and cannot identify which Raven in a multi-Raven region
was collected. Actor absence is also ambiguous. Neither is accepted as an
individual state oracle.

## Release gate

The static catalogue and N-entry router are complete offline. Release readiness is
blocked. Unknown state is hidden fail-closed. This prevents false remaining markers
but cannot meet fresh, mixed, completed, or pre-install save requirements until a
read-only unloaded-instance oracle is proven.

The runtime exposes `CompletionistMapV105ResetRavenStates(source)` so a future save
lifecycle adapter can clear cached state before publishing the new save. Until that
adapter exists, no install package should be released or human runtime-tested as a
complete all-Ravens mod.

## Rebuild

Run:

```powershell
python tools/v0.10.5/extract-native-raven-catalogue.py
python tools/v0.10.5/test_raven_catalogue.py
python tools/v0.10.5/build-all-ravens-release-candidate.py
python tools/v0.10.5/build-all-ravens-release-candidate.py --check
```

All commands read game data and write only repository catalogue, audit, or ignored
build output.
