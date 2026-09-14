# Unloaded-state oracle: native persistence checkpoint (2026-09-15)

Branch: `codex/all-collectibles-production-research`

This note records the current proof boundary for the cold/unloaded collectible-state oracle. It intentionally distinguishes proven native architecture from hypotheses. **UNLOADED_STATE_ORACLE remains FAIL** until the persistent GameObject representation is deterministically joined to exact static/WAD catalogue identity and validated cold across regions/sessions.

## Proven save-side architecture

1. `core.pickle` leaves approved userdata unchanged after `engine.CanPickle(v)`; it does not convert a GameObject to a GUID/UID in Lua.
2. `pickle_driver` at `0x5AF8AD` invokes `package.loaded["core.pickle"].Pickle` and then writes the returned Lua state through native serializer `0x7E7F10`.
3. `0x7E7F10` is the real checkpoint Lua-state byte serializer (`tableref_root` evidence and caller-provided output-span accounting).
4. Userdata reaches native serializer function `0x7E9190` through internal TValue tag 7.
5. `0x7E9190` obtains the code-side Lua class, walks its parent chain through class `+0x48`, checks the class byte at `+0xA4`, reads the first non-null callback at class `+0xB8`, and invokes that callback indirectly around `0x7E9298`.
6. Therefore **CodeSideLuaClass `+0xB8` is proven to be the per-class persistence encoder callback slot**.
7. The callback emits a bounded native payload which `0x7E9190` copies into the checkpoint stream.

## Proven runtime-token limitation

The GameObject Lua token remains runtime allocator state, not static WAD identity:

```text
bank   = dword[object+0x284] & 0xFFFFF
flavor = (dword[object+0x278] >> 3) & 1
low    = word[object+0x280]
token  = (((bank << 1 | flavor) << 16 | low) << 1) | 1
```

The inverse path through `0x5F9350 -> 0x4EF0B0` resolves allocator slot/type/family state. It must not be hardcoded as persistent identity.

## Proven restore-side observation (new primary lead)

Exact disassembly of the archived `unpickle_driver` function `0x5B1030-0x5B12CA` proves that it loads native address **`0x7E6DC0`** into a Lua TValue as a C function before the later unpickle-table processing:

```text
0x5B1131  mov rdi,[rbx+0x58]
0x5B1135  mov rcx,[rdi+0x10]
0x5B1139  call 0x9EAE10
...
0x5B1148  lea r8,[0x7E6DC0]
...
0x5B1152  call 0x9EAE10
...
0x5B1161  call 0x9F4CF0
...
             TValue tag set to 0x16 (Lua C function)
```

**Proven:** `0x7E6DC0` is inserted/pushed as a native Lua C function by the actual unpickle driver.

**Not yet proven:** the semantic claim that `0x7E6DC0` is specifically the checkpoint byte-to-Lua decoder. It is currently the highest-priority candidate because of its position before `__PickleTable` / `__SoftPickleTable` reconstruction and later restore bookkeeping.

The same unpickle driver later calls `0x7EABD0` at `0x5B1218`. Because this occurs after the earlier Lua-function setup and table handling, `0x7EABD0` should be treated as a later unpickle helper/finalization candidate, not assumed to be the byte decoder.

## Reusable static index

The one-time Capstone/SQLite index completed successfully and is local working data:

`./.research-index/gow-caebcb027980.sqlite`

Indexed surface from the successful build:

- 51,869 `.pdata` functions
- 34,510 strings
- 148,719 direct call/jump edges
- 27,415 indirect calls
- 141,085 RIP references
- 985,485 memory references
- 371,006 immediate image references
- 493 extracted Lua files / 6,050 relevant Lua hits
- 157,250 game-file manifest entries

The index intentionally does not claim standalone coverage for executable leaf code outside `.pdata`. An exact RVA can still be located through RIP/immediate references even if no runtime-function record covers its body.

## Corrected index-analysis bug

The first persistence-index follow-up incorrectly filtered `mem_refs.access` with `LIKE '%W%'`. Capstone stores access as a numeric bitmask (`CS_AC_READ=1`, `CS_AC_WRITE=2`). The analysis tool has been corrected to use `(access & 2) != 0`.

## 0x409FC0 candidate status

The reusable index found a decoded `+0xB8` assignment in giant function `0x406820-0x409E16`:

```text
0x409B73  lea rsi,[rip+...] -> 0x409FC0
0x409B85  mov [rbp+0xB8],rsi
```

The same large function also reaches known GameObject/unpickle infrastructure. However:

- it has no exact `GameObject` string ownership proof for that assignment;
- the function is mixed and also references deferred-hook infrastructure;
- `0x409FC0` has no standalone `.pdata` function row in the current index.

Therefore **`0x409FC0` is NOT proven to be the GameObject persistence callback** and must remain only a candidate/possible unrelated class callback.

## Next deterministic query

Use the reusable index to analyze the inverse path, centered on:

- `0x5B1030` unpickle driver
- `0x7E6DC0` native Lua C-function candidate deserializer
- `0x7EABD0` later unpickle helper
- `0x5B2324` OnUnpickleInternal wrapper
- `0x4EF0B0` GameObject token resolver
- `0x5F9350` Lua GameObject unboxer
- `0x60B9C0` token packer
- serializer reference points `0x7E7F10`, `0x7E9190`, `0x7E9340`

The index-only analyzer `tools/v0.10.5/analyze-gow-unpickle-index.py` correlates forward reachability from the candidate deserializer with reverse reachability to the GameObject resolver/unbox/token path, interesting class/string references, indirect calls, and small class-layout offsets. This is deliberately an inverse-path query, not another full EXE scan.

## Acceptance remains unchanged

Do not mark the unloaded oracle PASS until a stable native payload is deterministically associated with exact static/WAD identity and independently validated with:

- Veithurgard exact Raven states `false / true / true`;
- RegionSummary `2/3` as independent aggregate validation;
- a second region exact-object validation;
- actual cold/nonresident state;
- fail-closed unknown behavior;
- target script restored;
- second-session stability.
