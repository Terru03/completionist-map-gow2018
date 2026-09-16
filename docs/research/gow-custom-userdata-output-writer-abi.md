# GoW 2018 custom-userdata serializer output writer ABI

Status: **proven from the `0x5AF8AD` pickle driver around `0x5AFAB0 -> 0x7E7F10`**

Target executable SHA-256:

`caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`

## Result

`0x7E7F10` does not return a separate output-buffer pointer. It serializes the
custom-userdata carrier **in place** through a small caller-owned writer
descriptor passed in `R8`.

The caller initializes that descriptor immediately before the call:

```asm
5AFA8D  lea  rax,[r12+r15]
5AFA91  mov  [rsp+30h],r12
5AFA96  xor  ebx,ebx
5AFA98  mov  [rsp+38h],rax
5AFA9D  lea  r8,[rsp+30h]
5AFAA2  mov  [rsp+48h],rbx
5AFAA7  mov  [rsp+50h],bl
5AFAAB  mov  [rsp+40h],r12
5AFAB0  call 7E7F10h
5AFAB5  test al,al
5AFAB7  jne  5AFAh
```

This establishes the writer shape:

| Writer offset | Proven structural role |
| --- | --- |
| `+0x00` | output start pointer |
| `+0x08` | output end pointer / capacity bound |
| `+0x10` | current output cursor |
| `+0x18` | zero-initialized scratch/status qword; exact semantics not yet named |
| `+0x20` | zero-initialized scratch/status byte; exact semantics not yet named |

At the call site:

```text
start    = r12
end      = r12 + r15
cursor   = r12
capacity = r15
R8       = &writer
```

`AL` is a success boolean. The caller traps on failure and, after success,
computes the exact serialized carrier length directly from the writer:

```asm
5AFAC5  mov eax,[rsp+40h]   ; final cursor
5AFAC9  sub eax,[rsp+30h]   ; final cursor - start
5AFACD  mov [rdi],eax       ; used byte count
```

So the exact output region is:

```text
[start, cursor)
```

and:

```text
used_length = cursor - start
```

The same caller later compares the used length against the supplied buffer
capacity and emits the existing diagnostic strings:

```text
Pickled Lua state '%s', used %d bytes.
Failed to pickle Lua state '%s'. Pickle size is %d, but buffer is only %d.
```

## Why this matters

This closes the save-side carrier handoff. A runtime capture or static caller
trace no longer needs to guess where `0x7E7F10` put its output:

1. read the writer pointer passed in `R8`;
2. record `writer.start` before/after the call;
3. record the final `writer.cursor`;
4. the complete custom-userdata carrier is exactly `cursor - start` bytes from
   `start`.

For offline work, the carrier grammar recovered in
`gow-custom-userdata-record-contract.md` is now strong enough to scan a larger
save/evidence buffer for candidate carrier starts and infer the exact end from
the header, compressed payload, metadata framing, and fixed tables.

The companion scanner is:

`tools/v0.10.5/gow-custom-userdata-carrier-scan.py`

Self-test:

```powershell
python .\tools\v0.10.5\gow-custom-userdata-carrier-scan.py selftest
```

Scan a larger file:

```powershell
python .\tools\v0.10.5\gow-custom-userdata-carrier-scan.py scan .\candidate.bin `
  --output .\carrier-scan.json
```

The scanner rejects candidates unless the compressed section expands to the
header-proven exact decompressed length and the remainder can be framed into
valid metadata, size/offset tables, and trailing rows. By default, every
reconstructed userdata record must also be valid.

## Remaining narrow gap

The serializer's in-memory output ABI is solved. The remaining practical task
is locating this `[start,cursor)` carrier within archived/raw save material and
then correlating its record-level delta with the clean Raven alive/dead oracle.
No additional gameplay capture is required merely to establish the writer ABI.
