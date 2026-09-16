# Raven GameObject codec closure

Status: **closed for the frozen Raven save vectors**.

Ground-truth runtime evidence was captured in commit `f0757771d6c077bcd5cc0e7cda94d99cfbce3aaf` from GoW's native decoder path using an in-thread passive hook at RVA `0x5493A1`. The capture did not use the failed synthetic remote-thread decoder call. The hook was removed after capture and the original GoW bytes were restored.

Evidence file:

`archive/field-logs/runtime/raven-gameobject-token-resolver-20260916-173709/raven-gameobject-token-resolver.json`

## Frozen mappings

All three serialized records use flag `0x01` and the same registry hash `0x4EC230253427B2B0`.

| Object hash | Numeric registry | Slot | Packed token | Exact 17-byte payload |
| --- | ---: | ---: | --- | --- |
| `0x165CD520758061E5` | 238 | 1796 | `0x000000001C1001DD` | `01b0b227342530c24ee561807520d55c16` |
| `0xADB72E5C5003A8A0` | 238 | 1810 | `0x000000001C4801DD` | `01b0b227342530c24ea0a803505c2eb7ad` |
| `0x98BE1707BA2D65A9` | 238 | 1772 | `0x000000001BB001DD` | `01b0b227342530c24ea9652dba0717be98` |

For all three mappings, bit 17 (`aux`) is zero and the optional upper/flavour field is zero.

## Packed GameObject layout

The real `0x5491A0` decoder CFG establishes the relevant packed-token fields:

- bit 0: present marker
- bits 1-16: registry (`16` bits)
- bit 17: auxiliary flag
- bits 18-37: slot (`20` bits)
- bits 38-43: optional upper/flavour field (`6` bits)

Extraction:

```python
registry = (token >> 1) & 0xFFFF
aux      = (token >> 17) & 1
slot     = (token >> 18) & 0xFFFFF
flavour  = (token >> 38) & 0x3F
```

For these flag-`0x01` Raven records (`aux=0`, `flavour=0`):

```python
token = 1 | (registry << 1) | (slot << 18)
```

This reconstructs all three native runtime tokens exactly.

## Codec model

The two 64-bit values serialized in a flag-`0x01` record are **lookup keys**, not arithmetic encodings of the numeric registry and slot. They must not be treated as invertible hashes.

The generalised save-codec abstraction is therefore lookup-driven:

1. **Decode:** parse `(registry_hash, object_hash)` from the serialized record, resolve that hash pair through the GameObject lookup mapping to `(registry, slot)`, then pack the GameObject token.
2. **Encode:** unpack `(registry, slot, aux, flavour)` from the token, reverse-resolve `(registry, slot)` to `(registry_hash, object_hash)`, then emit the serialized record.

For the frozen Raven flag-`0x01` vectors, the exact payload is:

```python
bytes([0x01]) + registry_hash.to_bytes(8, "little") + object_hash.to_bytes(8, "little")
```

The forward and reverse lookup mapping is bijective for the three captured Raven entries, so each vector has a deterministic exact-byte inverse.

## Offline proof

`tools/v0.10.5/verify-raven-gameobject-codec-roundtrip.py` consumes the frozen native runtime evidence and verifies, without launching the game:

- the evidence source/build and native-capture verification flags;
- every payload/hash/registry/slot/token ground-truth value;
- packed-token reconstruction;
- token field extraction;
- forward `(registry_hash, object_hash) -> (registry, slot)` lookup;
- reverse `(registry, slot) -> (registry_hash, object_hash)` lookup;
- `payload -> token -> identical payload` for all three records.

The expected terminal result is:

```text
PASS: Raven GameObject codec exact-byte round-trip verified for all frozen runtime mappings.
```

## Closure conclusion

The previously missing numeric Raven GameObject identities are now known and the 17-byte representation has an exact deterministic inverse for every frozen Raven vector. Combined with the already reconstructed outer custom-userdata carrier, no additional runtime capture is required for this Raven codec issue.
