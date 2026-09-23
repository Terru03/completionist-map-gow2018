# Ship Head frozen staged identity, 2026-09-23

The offline replay at `tools/v0.10.5/ship_head_staged_identity.py` reads the
frozen staged WAD capture, the catalogue, and seven shipped WADs. It checks
the Ship Head `goProtoArtifactScript_Root` record ID in each WAD. For every
catalogue transform path it hashes each owner-chain subset that contains the
script carrier and the exact physical placement. Eight physical heads match
one state-only GameObject key each. Head 08 matches none of its two paths.
The full path, subset, hash, raw state, WAD digests, and capture digests are
in `ship-head-staged-identity.json`.

| Head | Frozen object hash | Raw state | Path hits |
| ---: | --- | --- | --- |
| 01 | `0xBECC6C40DB8D6DC5` | `0100004040` | 1/1 |
| 02 | `0x415D5E2E4B5CBC91` | `0100004040` | 1/1 |
| 03 | `0x0670C1234B277C01` | `0100004040` | 1/2 |
| 04 | `0x3607EBAE7B11E4AF` | `010000803f` | 1/1 |
| 05 | `0x5BF0302BD002420F` | `0100004040` | 1/2 |
| 06 | `0x1A5E4B6BD56B6B18` | `0100004040` | 1/1 |
| 07 | `0xC3373DF5E687D64B` | `0100004040` | 1/2 |
| 08 | none | none | 0/2 |
| 09 | `0xE82841BEC7B6D5A9` | `0100004040` | 1/1 |

The scalar bytes encode 3.0 in seven matched rows and 1.0 in head 04. The
shipped script defines `ACQUIRED = 3`; this capture is one frozen observation.
It does not prove a read-only unloaded state query, a save lookup for head 08,
stock marker suppression, or Ship Head-specific visual IDs. Runtime generation
stays `BLOCKED_FAIL_CLOSED`.
