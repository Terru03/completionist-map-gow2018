# Collectible changed-stream semantic fingerprint

Status: **CHANGED_STREAMS_FINGERPRINTED**

This probe sequence-aligns zlib streams only inside changed aligned save slots. It emits hashes, sizes, ordinals, known checkpoint-field labels, and allowlisted engine-style identifiers. It does not emit arbitrary save bytes and does not infer completion state.

## Summary

- Validated zlib streams: A=1267, B=1268
- Changed aligned slots: 6, 16
- Sequence-aligned changed runs: 2
- Runs containing previous slot-6/index-49 adjacency anchor: 1
- Known story/context identifiers found: BOAT_CONTEXT_CONFIG_NORMAL, LEAD_THE_WAY_BEHAVIOR_CONTEXT_CONFIG
- Changed runs with Raven/Odin identifiers: 0
- Runtime generation allowed: **false**

## Changed runs

### Slot 6 run 1 — replace A[49, 50] B[49, 50]

- Previous adjacency anchor: true
- Classification hints: story_behavior_context_lead
- Tokens only A: BOAT_CONTEXT_CONFIG_NORMAL
- Tokens only B: LEAD_THE_WAY_BEHAVIOR_CONTEXT_CONFIG
- Shared safe tokens: none
- A stream 49: off=202684 compressed=1474 decompressed=3205 sha256=22219a7b8240d054c99c13eee1511f82526dbd5fe453d01c3128dee389834092 fields=state
- B stream 49: off=202060 compressed=1399 decompressed=3014 sha256=085c5e81f2f23910efe06ff24a6ce2b7f8f63078f9acbc077dd3802503847e69 fields=state

### Slot 16 run 1 — insert A[0, 0] B[0, 1]

- Previous adjacency anchor: false
- Classification hints: story_behavior_context_lead
- Tokens only A: none
- Tokens only B: LEAD_THE_WAY_BEHAVIOR_CONTEXT_CONFIG
- Shared safe tokens: none
- B stream 0: off=202060 compressed=1399 decompressed=3014 sha256=085c5e81f2f23910efe06ff24a6ce2b7f8f63078f9acbc077dd3802503847e69 fields=state

## Target-field proximity to changed streams

- `ravenKilled`: A min=8 within4=0/1; B min=8 within4=0/1
- `state`: A min=0 within4=6/37; B min=0 within4=7/38
- `mapSummaryComplete`: A min=9 within4=0/29; B min=9 within4=0/29
- `bRuneReadStarted`: A min=None within4=0/0; B min=None within4=0/0
- `wellRead`: A min=None within4=0/0; B min=None within4=0/0
- `destroyed`: A min=7 within4=0/11; B min=7 within4=0/11
- `keysUsed`: A min=3 within4=2/8; B min=3 within4=2/8
- `challengeComplete`: A min=3 within4=2/8; B min=3 within4=2/8

## Interpretation

A changed-run token can help determine what a structural save difference belongs to, but it cannot bind a persisted value to an individual collectible. Exact instance binding plus known opposite semantic states for that same object are still required before any state could be used by production runtime code.

Unknown collectible state remains hidden/fail-closed.
