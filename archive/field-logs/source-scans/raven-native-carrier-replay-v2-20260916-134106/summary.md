# Raven native carrier bidirectional replay v2

**Verdict:** `RAVEN_NATIVE_CARRIER_BIDIRECTIONAL_REPLAY_EXACT`

- Forward exact zlib levels: `[7, 8, 9]`
- Reverse exact zlib levels: `[7, 8, 9]`
- Raven string append offset: `29`
- Raven record insert index: `1`
- Raven record trailing identity: `0x98BE1707BA2D65A9`

The only opaque DEAD-side seed is the new 25-byte Raven record itself.
All carrier framing, prefix, table and compression changes are rebuilt deterministically.
