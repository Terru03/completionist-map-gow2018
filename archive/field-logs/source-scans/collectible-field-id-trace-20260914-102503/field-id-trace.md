# Collectible checkpoint field-ID structural trace

Status: **BLOCKED_STRUCTURAL_TRACE_ONLY**

This probe derives schema field IDs for known checkpoint fields and traces those IDs through the two frozen saves.
A hit is structural evidence only; it is not an individual completion oracle.

## Summary

- Validated zlib streams: A=1267, B=1268
- Unique derived 16-byte field IDs: 12
- Changed paired-stream structural candidates: 0
- Runtime generation allowed: **false**

## Schema occurrences

- `ravenKilled`: 4 parsed schema occurrences
- `state`: 140 parsed schema occurrences
- `mapSummaryComplete`: 126 parsed schema occurrences
- `bRuneReadStarted`: 0 parsed schema occurrences
- `wellRead`: 0 parsed schema occurrences
- `destroyed`: 32 parsed schema occurrences
- `keysUsed`: 0 parsed schema occurrences
- `challengeComplete`: 0 parsed schema occurrences

## Candidate counts

- `ravenKilled`: 0 changed paired-stream candidates
- `state`: 0 changed paired-stream candidates
- `mapSummaryComplete`: 0 changed paired-stream candidates
- `bRuneReadStarted`: 0 changed paired-stream candidates
- `wellRead`: 0 changed paired-stream candidates
- `destroyed`: 0 changed paired-stream candidates
- `keysUsed`: 0 changed paired-stream candidates
- `challengeComplete`: 0 changed paired-stream candidates

## Interpretation

The previous exact-identity probe found zero literal per-row identity representations. This trace therefore looks one layer lower, at schema field IDs. Even a changed field-ID-bearing stream cannot be mapped to a collectible row without an exact instance-record binding and a semantically validated value.

Unknown state remains hidden/fail-closed.
