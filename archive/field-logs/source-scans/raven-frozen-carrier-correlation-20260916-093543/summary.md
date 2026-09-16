# Frozen Raven carrier correlation

**Verdict:** `AMBIGUOUS_MULTIPLE_TARGETS`

At least one save contains multiple zlib streams with the expected compressed/decompressed sizes, so the target cannot be uniquely selected by size alone.

## Target streams

| Save | Expected relative offset | Exact size matches | Selected raw offset | zlib index (0/1 based) | Immediate native carrier | Slot-base delta |
|---|---:|---:|---:|---:|---|---:|
| ALIVE | 39272 | 48 | n/a | n/a | n/a | n/a |
| DEAD | 39203 | 3 | n/a | n/a | n/a | n/a |

## Whole-file native carrier scan

| Save | zlib streams | plausible headers tested | exact decompression hits | valid carriers |
|---|---:|---:|---:|---:|
| ALIVE | 1349 | 149263 | 219 | 256 |
| DEAD | 1430 | 149263 | 219 | 256 |

## Interpretation

- The decisive immediate-parent test uses the actual raw target offset, not the previously reported slot-relative number.
- `yes` means a complete carrier accepted by `gow-custom-userdata-carrier-scan.py` starts exactly 16 bytes before that zlib stream and declares the same compressed length.
- A non-zero slot-base delta is retained as evidence that the earlier offset was relative to an enclosing slot/buffer rather than the start of `game.sav`.
- A negative immediate-parent result does not discard the Raven evidence. It narrows the stream to another persistence layer or a nested/enclosing buffer.

Full machine-readable evidence is in `summary.json`; exact target compressed/decompressed bytes and local contexts are archived beside this report.
