# All Ravens release gate

Status: `ready_for_runtime_test=false`

## Done offline

- 53-entry static native catalogue with schema and audit.
- Native world transforms and map-coordinate records.
- Data-driven marker generation across 22 region arrays.
- Current-realm filtering and shared Raven map resource.
- Exact collision object before exact UID routing.
- Single custom target with Raven, stock, and Nornir replacement paths.
- Per-Raven loaded-instance lifecycle and exact tracked-target cleanup.
- Bounded hit cleanup retry. No permanent polling.
- Save-cache reset API. Unknown state is hidden.
- Deterministic and LF/CRLF-stable five-file build.
- No progression or save writes.

## Blocker

No native read-only API has been proven for reading individual `ravenKilled` state
from an unloaded Raven WAD instance. The loaded-instance adapter cannot populate all
53 rows when a user opens a map, especially for Ravens killed before mod install.

## Exact next runtime probe

Build a read-only diagnostic that receives one catalogue instance GUID and queries
the native checkpoint/object-state store without loading or mutating that Raven.
Run it against two legitimate saves with opposite state for the same Raven. Prove:

1. The unloaded Raven returns `false` on the uncollected save.
2. The same unloaded Raven returns `true` on the collected save.
3. The query works before visiting its region.
4. Checkpoint restore changes the observed value back when expected.
5. No save, quest, marker, collectible, or progression bytes change.

Only after this passes should the adapter populate all catalogue rows and the full
human map/compass matrix begin.
