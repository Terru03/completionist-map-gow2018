# GoW 2018 custom-userdata decoded record contract

Status: **native save/restore record layer proven; outer carrier still partially unresolved**

Target executable SHA-256:

`caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`

Relevant native functions:

- save callback wrapper: `0x7E8EF0`
- decoded-record serializer: `0x7E9190`
- restore callback wrapper: `0x7E9550`
- decoded-record restore dispatch: `0x7E7B60`, with the decisive dispatch window at `0x7E7D7F..0x7E7E07`
- shared save/restore helper currently under investigation: `0x7E9012`

This document deliberately separates the **decoded record descriptor** from the
**outer save carrier**. The descriptor contract below is strong enough to build
and inspect records deterministically. The exact 16-byte carrier header,
compression framing, and remaining metadata must not be inferred from it.

## 1. Proven decoded descriptor

The native descriptor consumed by restore and populated by save contains:

| Descriptor field | Meaning |
| --- | --- |
| `+0x20` | pointer to `u16[record_count]` record-offset table |
| `+0x28` | pointer to `u8[record_count]` stored-size table |
| `+0x30` | pointer to record blob |
| `+0x38` | `u16` record count |
| `+0x3A` | `u16` current/final record-blob length |

All integer fields observed in the serialized tables are little-endian on the
supported x86-64 build.

For record index `i`:

```text
offset = u16_le(offset_table[i])
size   = u8(size_table[i])

record = blob[offset : offset + size]

record[0:8] = u64_le CodeSideLuaClass key/reference
record[8:]  = class callback payload
```

Therefore:

```text
stored_size = payload_length + 8
payload_ptr = blob + offset + 8
payload_len = stored_size - 8
```

The phrase **CodeSideLuaClass key/reference** is intentional. The dispatch code
proves that this qword is compared against qword keys in the global class
registry. It is not yet necessary to label its physical representation more
specifically than that.

## 2. Save side: `0x7E9190`

The save-side native serializer establishes the forward half of the contract.

The class metadata chain is walked until the save callback is found. The
relevant persistence callback slot is `CodeSideLuaClass + 0xB8`.

The serializer:

1. invokes the `+0xB8` callback into a bounded temporary payload buffer;
2. obtains the callback payload length;
3. writes the class key/reference as the first qword of the record;
4. copies the callback payload immediately after that qword;
5. stores `payload_length + 8` into the byte-sized size table;
6. stores the current blob position into the 16-bit offset table;
7. advances the descriptor record count and blob length.

The observed native save-side limits are:

```text
record_count          <= 512
record_blob_length    <= 0x3000
callback_payload      <= 0x80
stored_record_size    <= 0x88 for the proven callback buffer
```

The byte-sized size table itself can represent at most `0xFF`, but the proven
save callback buffer imposes the tighter `0x80 + 8 = 0x88` native-output limit.

## 3. Restore side: `0x7E7D7F..0x7E7E07`

Restore independently proves the inverse.

The decisive native flow is:

```text
record_index       = u16[*entry]
record_size        = u8[descriptor->sizes + record_index]
record_offset      = u16[descriptor->offsets + 2*record_index]
record_blob_base   = descriptor->blob
class_key          = u64[record_blob_base + record_offset]

payload_pointer    = record_blob_base + record_offset + 8
payload_length     = record_size - 8
```

The class key is looked up in the global `CodeSideLuaClass` registry. If needed,
restore walks the class-parent link at `+0x48`. The restore callback is taken
from `CodeSideLuaClass + 0xC0` and receives:

```text
rcx = restore state
rdx = payload pointer
r8  = payload length
```

The dispatch is a tail jump to the resolved callback.

This is the strongest symmetry result in the persistence work so far:

```text
save:    class +0xB8 -> [key][payload], size = payload + 8
restore: [key][payload], size - 8 -> class +0xC0
```

## 4. Outer carrier: what is already proven

`0x7E8EF0` and `0x7E9550` are registered as the corresponding save and restore
handlers for the same callback registrations.

The save wrapper calls the decoded-record serializer at:

```text
0x7E8F70 -> 0x7E9190
```

The restore wrapper receives its serialized input in `r8`. Its cursor starts at:

```text
rsi = input + 0x10
```

so the outer carrier begins with a 16-byte header.

The restore dataflow currently proves these header-dependent operations:

```text
word[input + 0x02]
    added to the decompressed-output base to locate descriptor->record_blob

word[input + 0x08]
    record count used to copy:
      count bytes      -> descriptor +0x28 size table
      count * 2 bytes  -> descriptor +0x20 offset table

word[input + 0x0E]
    added to the serialized cursor after the compression/inflate section
```

Restore calls the inflate/parser routine at `0x9C6480`, with the serialized
cursor as input and a separate output buffer.

After the compressed section, restore consumes the record-size table, then the
record-offset table, and later advances by six bytes for each row in another
descriptor/metadata section.

The shared helper `0x7E9012` is reachable from both save and restore paths. That
makes it relevant infrastructure, but its exact semantic role is **not yet
proven**. It should not be named as carrier setup/finalization until its writes
are reconstructed.

## 5. What is not yet proven

Do not encode any of the following as facts yet:

- semantic names for all fields in the 16-byte outer header;
- exact deflate/compression-side function paired with restore's `0x9C6480`;
- exact meaning/layout of the six-byte-per-row metadata section;
- whether the known Raven 79-byte / 116-byte decompressed zlib stream is itself
  this native carrier, a sub-buffer inside it, or a different persistence
  stream;
- a raw-save-file patching algorithm.

Those are the remaining carrier-layer questions.

## 6. Deterministic descriptor tool

`tools/v0.10.5/gow-custom-userdata-descriptor.py` operates only on the proven
decoded descriptor components.

Self-test:

```powershell
python .\tools\v0.10.5\gow-custom-userdata-descriptor.py selftest
```

Inspect three already-extracted components:

```powershell
python .\tools\v0.10.5\gow-custom-userdata-descriptor.py inspect `
  --sizes .\sizes.bin `
  --offsets .\offsets.bin `
  --blob .\blob.bin `
  --serializer-compatible `
  --require-contiguous
```

Build components from JSON:

```json
{
  "records": [
    {
      "class_key": "0x1122334455667788",
      "payload_hex": "AABBCC"
    }
  ]
}
```

```powershell
python .\tools\v0.10.5\gow-custom-userdata-descriptor.py build `
  --input .\records.json `
  --out-dir .\descriptor-out
```

The builder emits:

```text
sizes.bin
offsets.bin
blob.bin
manifest.json
```

and immediately parses its own output with the strict native-compatible checks.
It is therefore useful now even before the outer carrier is solved.

## 7. Next static-analysis target

The next pass should be narrow:

1. reconstruct the complete `0x7E8EF0` save-wrapper control/data flow;
2. reconstruct `0x7E9012` without assigning semantics in advance;
3. identify the save-side peer of restore's `0x9C6480` compression call;
4. map every write that produces the 16-byte header and the post-compression
   tables/rows;
5. compare the resulting writer layout directly with the `0x7E9550` reader;
6. only then apply the carrier parser to the Raven alive/dead oracle.

No new gameplay capture is needed for this stage.
