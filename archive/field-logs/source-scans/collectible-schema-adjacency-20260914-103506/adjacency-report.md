# Collectible schema-adjacency structural trace

Status: **STRUCTURAL_ADJACENCY_LEADS**

This is a read-only structural probe. A stable schema descriptor next to a changed zlib stream is only an addressing lead; it is not completion state.

## Summary

- Validated zlib streams: A=1267, B=1268
- Changed aligned slots: 6, 16
- Stable target-schema descriptor pairs: 1009
- Descriptor pairs with changed neighbors within ±4: 5
- Candidates located in changed aligned slots: 5
- Runtime generation allowed: **false**

## Stable descriptor pairs by field

- `ravenKilled`: 22
- `state`: 566
- `mapSummaryComplete`: 458
- `bRuneReadStarted`: 0
- `wellRead`: 0
- `destroyed`: 169
- `keysUsed`: 122
- `challengeComplete`: 122

## Candidate overview

1. slot 6 fields `state`, `keysUsed`, `challengeComplete`; descriptor indexes A=45 B=45; same descriptor offset=true; changed neighbor deltas=[4]
2. slot 6 fields `state`, `keysUsed`, `challengeComplete`; descriptor indexes A=46 B=46; same descriptor offset=true; changed neighbor deltas=[3]
3. slot 6 fields `state`; descriptor indexes A=47 B=47; same descriptor offset=true; changed neighbor deltas=[2]
4. slot 6 fields `state`; descriptor indexes A=48 B=48; same descriptor offset=true; changed neighbor deltas=[1]
5. slot 6 fields `state`; descriptor indexes A=51 B=51; same descriptor offset=true; changed neighbor deltas=[-2]

## Interpretation

The previous probes ruled out literal per-instance identities and literal 16-byte checkpoint field IDs in candidate state payloads. This probe tests the narrower possibility that a stable schema descriptor addresses a nearby payload positionally. Any result remains structural only until an exact object binding and known opposite semantic states prove the value encoding.

Unknown collectible state remains hidden/fail-closed.
