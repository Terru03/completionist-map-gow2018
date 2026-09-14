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

## Native Lua persistence investigation

Offline PE registration-table analysis of the shipped PC executable proved that the
Lua-facing `game.SubObject` table exposes exactly these seven methods in the relevant
registration block:

- `Sleep`
- `Wake`
- `SetRetainOnCheckpoint`
- `SetForgetOnCheckpoint`
- `SoftSave`
- `SetEntityZoneHandler`
- `SetUpdateDisableDistance`

`LoadSubObject` exists as an internal engine string but is not registered as a Lua
method. The registered object lookup APIs operate on loaded game objects; the scan
found no read/restore/GUID API for querying checkpoint state of an unloaded subobject.
Evidence is archived under
`archive/field-logs/source-scans/lua-registration-tables-20260914-065951/`.

For release purposes, the supported Lua/native API route is therefore considered
closed unless new concrete engine evidence appears. This does **not** prove that the
compiled engine lacks an internal mechanism; it means the mod has no proven callable,
read-only Lua oracle for it. Unknown per-Raven state remains hidden/fail-closed.

## Runtime gate remains closed

Do not populate static Raven pins from aggregate regional counts, actor absence, map
discovery, or synthetic completion state. `ready_for_runtime_test` remains `false`
until an exact individual unloaded-state oracle is proven. Loaded Raven lifecycle
observation remains valid but cannot establish pre-install kills for all 53 entries.
