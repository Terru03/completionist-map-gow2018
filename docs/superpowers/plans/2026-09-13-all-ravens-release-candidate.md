# All Ravens Release Candidate Plan

## Goal

Scale proven v3.3 Raven marker, routing, and lifecycle behavior from one real Raven to every native Odin's Raven location. Keep progression read-only. Build only an offline release candidate; do not install or launch game.

## Safety gates

- Start from `fcee0241f4258b0195c2b54eae6f18a2b4d2b367` on `codex/all-ravens-release-candidate`.
- Treat static native identity/position and runtime collected state as separate data.
- Never infer Raven ownership from `currMarkerID` alone.
- Reject duplicate UIDs, incomplete catalogue rows, unknown state, and tampered input.
- Keep `ready_for_runtime_test=false` until every catalogue row has a proven individual read-only state oracle.
- Never write game files, saves, or progression during development or tests.

## Work

1. Extract every Raven instance from native level WAD records. Rebuild world transforms through static scene-parent chains. Preserve v3.3 Veithurgard marker identity and coordinate.
2. Map native parent quest keys to realm and region records. Record WAD hashes, object GUIDs, record IDs, transform sources, and state-adapter evidence.
3. Generate canonical JSON catalogue plus machine-readable audit. Validate expected count, distributions, identities, coordinates, realms, state adapters, and sources.
4. Generalize v3.3 marker build, selection router, and persistent gameplay lifecycle to catalogue-driven Raven identities. Preserve exact candidate-object plus UID confirmation and one active target.
5. Add fresh, mixed, complete, kill, restore, stale-selection, stock, Nornir, teardown, deterministic-build, newline, transaction, recovery, tamper, and no-progression-write tests.
6. Run targeted and broad suites. Review security-sensitive installer and binary-patch changes. Build deterministic candidate twice and publish hashes/audits.
7. Commit logical milestones. Do not merge `main`.

## Native state decision

Preferred oracle is each Raven object's own checkpoint-persisted `ravenKilled` field, keyed by its native static instance identity. Production use needs proof that this state can be read for unloaded Raven WADs. If native APIs expose only loaded objects or region aggregate counts, stop release gate and document exact blocker; do not guess individual state.
