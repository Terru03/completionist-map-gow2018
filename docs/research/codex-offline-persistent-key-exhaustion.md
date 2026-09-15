# Offline persistent-key exhaustion result

## Result

Offline routes are exhausted to one load-time join. No exact tuple is claimed:

- `BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY`
- `BLOCKED_EXACT_UNLOADED_STATE_ORACLE`

The machine-readable proof is
`docs/research/codex-offline-persistent-key-exhaustion.json`. The tracer verifies
37 exact instruction-byte anchors against supported `GoW.exe` SHA256
`caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`,
10 call edges in the existing SQLite index, the target WAD hash, and the exact
canonical record.

## Route A: scheduler construction

`0x85A420` constructs the scheduler lists.

The outer node layout is:

| Offset | Meaning | Evidence |
| --- | --- | --- |
| `+0x00/+0x08` | global-list links | tail insertion `0x85A524..0x85A543` |
| `+0x10` | WAD registry ID | `0x85A546 -> 0x4FE020`; WAD `+0xC3C` load `0x85A54B`; store `0x85A558` |
| `+0x18` | loaded type-`0x116` config | lookup `0x85A4D6..0x85A4DF`; store `0x85A55B` |
| `+0x20` | inner-list sentinel | initialized `0x85A510..0x85A517` |
| `+0x30` | incoming config resource hash | store `0x85A551` |
| `+0x38..+0x3D` | progress/complete/disabled state | zero stores `0x85A55F..0x85A563` |
| `+0x40` | exact WAD pointer | store `0x85A568` |
| `+0x48` | scheduler time state | zero store `0x85A56C` |

An outer is unique by resolved WAD context plus WAD `+0x1D8`.
`0x85A610` walks the global list and compares those fields. A repeated constructor
call returns the prior outer, so later resource hashes do not rebuild it.

The constructor reads config count at `config+0x08`. It allocates one inner per
config-array element and inserts it at the outer list tail in array order at
`0x85A580..0x85A5EA`. Inner `+0x10` is the config-array pointer, `+0x18` is the
outer, and `+0x20..+0x40` is zeroed runtime state. No sort or shuffle occurs.
The driver walks both lists forward and passes outer/inner indices to `0x858320`
at `0x85AEE3`. Frame budget changes how many items run in a frame, not their
relative list order.

Inside `0x858320`, inner `+0x10` supplies the config. Config `+0x38/+0x40` is a
variant pointer array/count. Each variant weight is byte `+0x10`. The LCG at
`0x85847E..0x8584E0` chooses one weighted variant within that already selected
inner item. The chosen variant supplies a string at `+0x4C`, which is hashed and
resolved as resource type `0x352` at `0x8585DF..0x8586A6`. Thus the LCG can
change the chosen prototype, but it neither sorts nor chooses the scheduler
item.

The exact canonical scene pair is:

- override index `9631`, offset `0x32E3AB0`, holding exact GUID
  `95b9c644-4d47-9ac6-8207-b1829d02909b`;
- group start index `9632`;
- transform index `9633`, offset `0x32E3C60`, unique 164-byte payload, record ID
  `44c6b995c69a474d82b107829c90029d`.

The transform's prototype ID `f4f22e4546b2194891ad7f9a7c5b6dc4` occurs in
payloads at indices `8545`, `8548`, and `9633`. This proves prototype ancestry,
not a scheduler index. Scheduler nodes contain type-`0x116` config pointers and
a selected type-`0x352` resource; they contain no raw scene-record ID or physical
offset. No static edge found converts the unique override/final bytes into the
loaded config entry. Therefore `(outer_index, inner_index)` remains unavailable
offline.

## Route B: WAD metadata registry ID

`0x82CF00` first deserializes the existing 0xA8-byte metadata array through
`0x667380`, then reconciles it against 64 runtime WAD context slots, each
`0xEE28` bytes.

For each live WAD, `[WAD+0x50]+0x54` is its filename/path string. Existing record
lookup compares it exactly with record `+0x84` through `strcmp` at
`0x82D180..0x82D18D`. A match reads registry ID from record `+0x24` at
`0x82D1A9` and stores it to WAD `+0xC3C` at `0x82D203`.

The new-record path appends at the current metadata count. It copies the same
filename to `+0x84`, computes `record_index + 0x12` at `0x82D300..0x82D321`, and
stores the current 64-slot runtime context ordinal to `+0x28` at `0x82D34F`.
So `+0x28` is a mutable runtime slot ordinal, not a registry ID or static WAD
ordinal.

The exact WAD-to-metadata key is now proved. Exact registry ID is not: existing
order comes from a runtime-deserialized array, while new order comes from current
runtime WAD-context occupancy. Neither order exists in
`alf355_chiseldungeon.wad` physical records.

Both frozen saves were checked without opening active saves. The first contained
1,267 validated zlib streams and the second 1,268. Exact ASCII and UTF-16LE
forms of `alf355_chiseldungeon.wad` and `WAD_ALF355_CHISELDUNGEON` had zero hits
in raw containers and all validated streams. These saves therefore do not expose
the metadata filename table through the supported decompression path.

## Route C: allocation/free ancestry

Scheduler list order is stable after construction, but it is not enough to
derive a slot. `0x4EF110` is the GameObject release path. It obtains registry ID
from object `+0x280` at `0x4EF21E`, chooses flavor from object `+0x278`, obtains
slot from `+0x284`, clears the bank qword at `0x4EF27D`, and decrements live
count at `0x4EF281`. The SQLite index has six direct entries:

- `0x4EF19B`
- `0x54FF3E`
- `0x60DA17`
- `0x60EA32`
- `0x60ED16`
- `0x8100FB`

This rules out a safe “Nth scheduled item means slot N” shortcut. Before the
canonical event, the missing subset is exact: the type-`0x116` items preceding
the canonical item, their weighted type-`0x352` choices, all successful same-WAD
allocations, and any release among those objects. Physical record index `9633`
cannot supply this sequence.

## Route D: frozen saves

Routes A-C produced no exact registry ID, slot range, ordinal, or token
candidate. Testing arbitrary `__subobjs` tokens would be brute-force narrative,
so no new `savedInfo.ravenKilled` binding is claimed. The filename-table negative
check above is the only justified new save result.

## Route E: live startup hardening

The capture tool now has a non-invasive `preflight` command. It checks the EXE
and WAD hashes, all capture instruction anchors, exact canonical record, 64-bit
Python, and x64 ctypes structure layouts without attaching to a process. All
used Toolhelp, debug, handle, thread, and cache APIs now have explicit ctypes
argument and result types.

The wrapper runs preflight and archives `preflight.json` before launching the
game. If preflight fails, the game is not launched. Python stdout/stderr remains
archived. Startup prints exact stages for `OpenProcess`, `Module32FirstW`,
`DebugActiveProcess`, and breakpoint installation. `Debugger ready` now prints
only after attach, kill-on-exit protection, breakpoint install, and initial
registry snapshot succeed. Attach/startup exceptions still run cleanup and write
failure JSON.

## Narrow remaining edge

```text
canonical override/final record pair
  -> loaded type-0x116 inner config entry
  -> selected type-0x352 resource and exact loader event
  -> complete preceding same-registry allocation/release sequence
```

The first arrow requires load-time relocation/runtime state absent from the WAD
physical catalogue and frozen saves. Next live capture must observe it. Even an
identical token on two reloads remains supporting evidence only until preceding
causal history is complete.
