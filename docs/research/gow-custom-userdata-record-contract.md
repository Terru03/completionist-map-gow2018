# GoW 2018 custom-userdata persistence contract

Status: **decoded record layer proven; outer carrier framing substantially proven; remaining gaps are metadata semantics, exact compressor identity, and raw-save embedding**

Target executable SHA-256:

`caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`

Relevant native functions:

- outer save carrier builder: `0x7E7F10`
- variable tagged-metadata writer: `0x7E83D0`
- save-side compression wrapper: `0x7E8540`
- decoded userdata-record serializer: `0x7E9190`
- outer restore carrier reader: `0x7E9550`
- decoded record restore dispatch: `0x7E7B60`, decisive window `0x7E7D7F..0x7E7E07`
- local callback path: `0x7E8EF0`
- tiny shared local helper still semantically unnamed: `0x7E9012`

The important correction from the carrier-symmetry pass is that `0x7E8EF0` is **not**
the main outer-carrier builder. `0x7E7F10` writes the complete carrier consumed
by `0x7E9550`. The two functions mirror one another closely enough to recover
the binary framing without assigning speculative game-level meanings to every
field.

## 1. Proven decoded descriptor

The descriptor consumed by restore and populated by save contains:

| Descriptor field | Meaning |
| --- | --- |
| `+0x20` | pointer to `u16[record_count]` record-offset table |
| `+0x28` | pointer to `u8[record_count]` stored-size table |
| `+0x30` | pointer to record blob |
| `+0x38` | `u16` record count |
| `+0x3A` | `u16` current/final record-blob length |

All serialized integer fields observed here are little-endian.

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

The phrase **CodeSideLuaClass key/reference** remains intentional. Native code
proves that this qword is compared with qword keys in the global class
registry. A narrower physical label is not needed for the parser.

## 2. Save-side decoded record: `0x7E9190`

The save serializer walks class metadata until it finds the persistence save
callback at `CodeSideLuaClass + 0xB8`.

It then:

1. invokes the callback into a bounded temporary payload buffer;
2. obtains the callback payload length;
3. writes the class key/reference as the first qword of the record;
4. copies the payload immediately after the key;
5. stores `payload_length + 8` in the byte-sized size table;
6. stores the current record-blob position in the 16-bit offset table;
7. increments descriptor record count and blob length.

Observed native save-side limits:

```text
record_count          <= 512
record_blob_length    <= 0x3000
callback_payload      <= 0x80
stored_record_size    <= 0x88
```

The size table can represent `0xFF`, but the proven save callback buffer imposes
the tighter native-output limit of `0x80 + 8 = 0x88`.

## 3. Restore-side decoded record: `0x7E7D7F..0x7E7E07`

Restore independently proves the inverse:

```text
record_index       = u16[*entry]
record_size        = u8[descriptor->sizes + record_index]
record_offset      = u16[descriptor->offsets + 2*record_index]
record_blob_base   = descriptor->blob
class_key          = u64[record_blob_base + record_offset]

payload_pointer    = record_blob_base + record_offset + 8
payload_length     = record_size - 8
```

The class key is looked up in the global `CodeSideLuaClass` registry. Restore
walks the class-parent link at `+0x48` when needed. The restore callback comes
from `CodeSideLuaClass + 0xC0` and receives:

```text
rcx = restore state
rdx = payload pointer
r8  = payload length
```

The native symmetry is therefore:

```text
save:    class +0xB8 -> [key][payload], size = payload + 8
restore: [key][payload], size - 8 -> class +0xC0
```

## 4. Proven 16-byte outer header

`0x7E7F10` constructs a 16-byte header and later copies it to the serialized
output as one 16-byte block. All eight fields are little-endian `u16`.

Neutral structural names are used where game-level semantics are not yet
proven:

| Offset | Structural meaning | Save-side source / restore use |
| --- | --- | --- |
| `+0x00` | `section0_word_count` | controls a post-compression section of `2 * value` bytes |
| `+0x02` | `record_blob_offset` | offset of record blob inside decompressed payload |
| `+0x04` | `metadata_pair_count` | number of variable metadata entries; each entry restores two tagged scalars |
| `+0x06` | `row_count` | number of trailing 6-byte rows |
| `+0x08` | `record_count` | number of size bytes and offset words |
| `+0x0A` | `record_blob_length` | record-blob byte length |
| `+0x0C` | `scalar_c` | copied through the header; exact semantics still unknown |
| `+0x0E` | `compressed_length` | byte length of compressed section immediately after header |

Header construction is visible at `0x7E80A0..0x7E80D6`. The whole header is
written at `0x7E8176..0x7E817D`.

Restore starts its body cursor at:

```text
rsi = input + 0x10
```

and advances past the compressed section with:

```text
rsi += u16_le(input + 0x0E)
```

so the 16-byte boundary and `compressed_length` are independently confirmed by
the reader.

## 5. Proven decompressed payload

Before calling the save-side compression wrapper, `0x7E7F10` constructs one
contiguous uncompressed buffer.

At `0x7E8102..0x7E8119` it copies:

```text
prefix length      = header.record_blob_offset
record blob length = header.record_blob_length

decompressed_payload =
    descriptor_prefix[0 : record_blob_offset]
    + record_blob[0 : record_blob_length]
```

It then calls the compression wrapper:

```text
0x7E813D -> 0x7E8540
```

Restore performs the inverse through its inflate/parser call at `0x7E9677` and
then establishes:

```text
descriptor->record_blob =
    decompressed_output + u16_le(header + 0x02)
```

Expected decompressed length is therefore:

```text
record_blob_offset + record_blob_length
```

The exact low-level compression identity is intentionally not frozen as a fact
yet. The current inspection tool tries standard zlib, gzip, and raw-deflate
framing and reports which, if any, succeeds.

## 6. Proven serialized body grammar

After the 16-byte header, save and restore now agree on this framing:

```text
+0x00  header[16]

+0x10  compressed bytes
       length = header.compressed_length

       section0 u16 words
       length = 2 * header.section0_word_count

       variable tagged metadata
       entry count = header.metadata_pair_count
       each entry contains TWO tagged scalars
       each tagged scalar occupies 2, 3, or 5 bytes total

       record-size table
       length = header.record_count bytes

       record-offset table
       length = 2 * header.record_count bytes

       trailing rows
       length = 6 * header.row_count bytes
```

Restore's fixed-table copies are decisive:

```text
0x7E97A4:
    cursor -> descriptor +0x28
    length = header.record_count

0x7E97BF:
    cursor -> descriptor +0x20
    length = 2 * header.record_count
```

and the row loop advances `rsi += 6` per row at `0x7E97E9`.

Save calls the variable-metadata writer at:

```text
0x7E820E -> 0x7E83D0
```

The reader loads each metadata tag from the serialized cursor, rejects values
outside `0..5`, and dispatches to one of three observed encoded widths:

```text
2 bytes total
3 bytes total
5 bytes total
```

The restore-side instruction windows around `0x7E96E0..0x7E972B` and
`0x7E972E..0x7E977C` show the two tagged-scalar decodes per entry.

The exact semantic meaning of tag values `0..5` is not yet named. That is no
longer required merely to locate the following record tables.

## 7. Deterministic metadata-boundary inference

Because every section after variable metadata has a header-proven fixed length,
the metadata span itself is recoverable from the total carrier length:

```text
fixed_tail =
    record_count
    + 2 * record_count
    + 6 * row_count

metadata_length =
    carrier_length
    - cursor_after_section0
    - fixed_tail
```

For `N = metadata_pair_count`, restore consumes exactly `2*N` tagged scalars.
Each scalar has width 2, 3, or 5 and tag byte `<= 5`.

Therefore a tool can infer the width used by each observed tag by requiring a
consistent tag->width assignment whose `2*N` tokens consume the metadata span
exactly. There are at most six tags and only three candidate widths, so the
search space is tiny (`3^6 = 729` before early pruning).

This is framing inference, not semantic guessing.

## 8. Tools

### Decoded descriptor

`tools/v0.10.5/gow-custom-userdata-descriptor.py`

Self-test:

```powershell
python .\tools\v0.10.5\gow-custom-userdata-descriptor.py selftest
```

It can inspect and build the proven `sizes / offsets / blob` components.

### Outer carrier

`tools/v0.10.5/gow-custom-userdata-carrier.py`

Self-test:

```powershell
python .\tools\v0.10.5\gow-custom-userdata-carrier.py selftest
```

Inspect an exact extracted carrier:

```powershell
python .\tools\v0.10.5\gow-custom-userdata-carrier.py inspect .\carrier.bin
```

Inspect a carrier embedded in a larger file:

```powershell
python .\tools\v0.10.5\gow-custom-userdata-carrier.py inspect .\input.bin `
  --offset 0x1234 `
  --length 0x5678 `
  --output .\carrier-report.json
```

The carrier inspector:

- decodes all eight header words;
- slices the compressed section and all fixed post-compression sections;
- infers candidate tag-width mappings from exact framing constraints;
- tries zlib/gzip/raw-deflate decompression without asserting a format in advance;
- validates decompressed length against `record_blob_offset + record_blob_length`;
- slices prefix and record blob;
- reconstructs record boundaries from the proven size/offset tables;
- reports each valid record's class key/reference and callback payload.

## 9. Remaining questions

The persistence problem is now narrower. The unresolved items are:

- semantic names for header `+0x00`, `+0x04`, `+0x06`, and `+0x0C` beyond their proven structural roles;
- semantic meanings of metadata tags `0..5`;
- exact semantics of the six-byte rows;
- exact low-level save compressor identity / framing accepted by `0x7E8540`;
- precise role of tiny helper `0x7E9012` and the archived call-vs-tail-jump CFG discrepancy around it;
- whether the known Raven 79-byte / 116-byte decompressed zlib stream is this carrier, a sub-buffer of it, or a different persistence stream;
- the carrier's exact location/embedding inside the raw save container.

The next useful step is **not** another broad scan. It is to run the outer
carrier inspector against archived candidate bytes where an exact carrier
boundary is available, then use the Raven alive/dead oracle to identify which
record or metadata entry changes. If the archive does not contain an exact
carrier byte slice, the next static pass should target only the writer output
length/buffer handoff from `0x7E7F10` into its caller so that the carrier can be
extracted deterministically from an existing save.
