# Exact frozen Raven stream resolution

**Verdict:** `EXACT_RAVEN_STREAMS_RESOLVED_NATIVE_CARRIER`

Both exact historical Raven streams are accepted as complete native custom-userdata carriers beginning 16 bytes earlier.

## Coordinate contract

- Slot index is zero-based.
- `relative_offset` is measured from the start of the complete slot stride, including its 208-byte header.
- Slot-local zlib stream index is zero-based and reproduced with the historical scanner algorithm.
- Exact stream identity is selected by `(slot_index, relative_offset)`, never by size alone.

## Exact targets

| State | Slot | Slot zlib index | Relative offset | Raw file offset | Compressed → decoded | Whole-file index | Header length signature | Full carrier scanner |
|---|---:|---:|---:|---:|---:|---:|---|---|
| ALIVE | 17 | 27 | 39272 | 28561136 | 73 → 79 | 1295 | yes | yes |
| DEAD | 18 | 27 | 39203 | 30238579 | 96 → 116 | 1376 | yes | yes |

## Why this closes the earlier ambiguity

The earlier broad pass found many same-size streams. This pass starts from the original slot-local coordinates and independently verifies offset, zero-based stream index, compressed size, decoded size, and DEAD Raven semantics. Same-size and same-payload duplicates are retained only as context.

## Immediate-header result

A matching compressed length plus `record_blob_offset + record_blob_length == decoded_length` is reported separately from full carrier acceptance. This distinction is intentional: it tells us whether the unresolved part is stream identity, the 16-byte header, or the post-compression tail grammar.

Machine-readable details and the exact compressed/decompressed bytes plus ±256-byte framing contexts are archived beside this report.
