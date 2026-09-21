# Astra High task: trace the missing Raven checkpoint stream after dual staged-channel negative

## Branch

Work only on:

`codex/all-ravens-release-candidate`

Do not merge to `main`. Do not switch to the all-collectibles branch. Commit and push every meaningful stage.

## Product goal

Finish authoritative Raven persistence for Completionist Map:

- fresh save: all 53 Ravens shown;
- advanced save: only surviving Ravens shown immediately at map-open;
- killed Raven disappears immediately;
- map-open/load reconstructs exact killed set from authoritative checkpoint/save state;
- no save/progression writes;
- exact identity only, fail closed on unknown.

## Read first

Read the latest branch and especially:

- `archive/field-logs/local-handoffs/raven-authority-handoff-20260920.md`
- `archive/field-logs/runtime-captures/staged-wad-dual-payload-raven-state-readonly-20260921-052345/report.txt`
- `archive/field-logs/runtime-captures/staged-wad-dual-payload-raven-state-readonly-20260921-052345/report.json`
- `archive/field-logs/source-scans/staged-wad-parallel-channels-20260920-212109/report.txt`
- `archive/field-logs/source-scans/raven-staged-restore-records-20260920-205034/report.txt`
- `archive/field-logs/local-handoffs/astra-raven-restore-interrupted-20260920/`

Reuse existing tooling and solved codecs under `tools/v0.10.5/`.

## What is already solved and must not be redone

Do NOT redo:

- all 53 Raven catalogue identities;
- GameObject 17/21-byte save-reference codec;
- custom-userdata carrier framing;
- frozen alive/dead Raven fixture decoding;
- Lua `ravenKilled` semantics;
- raw Lua backing-cache / allocator scans;
- ordinary `core.thunk` persistence searches;
- `engine.SerializeHook` detour;
- save-ring timestamp/newest-slot inference;
- nearest-coordinate matching;
- RegionSummary-only inference;
- generic direct-call graph scans.

Known VikingFuneral Raven:

- catalogue ID: `raven_642d0d164af0a5d4076e77933c549a5d`
- object hash: `0x98BE1707BA2D65A9`
- serialized identity: `01b0b227342530c24ea9652dba0717be98`

Known companion identities in `Xpl200_Funeral`:

```
01b0b227342530c24ee561807520d55c16
01b0b227342530c24ea0a803505c2eb7ad
```

## New evidence that changes the task

The global staged WAD table is proven:

- count: 425 records
- base: module `+0x22C7170`
- stride: `0xA8`
- shared payload pool base: module `+0x22C6940`
- pool used size: module `+0x22C6938`
- stable WAD key: record `+0x24`
- flags/state: record `+0x20`
- name/string storage: record `+0x84`

Two independent variable payload descriptors are statically proven:

### Channel A
- pointers: `record+0x30`, `record+0x38`
- byte size: `record+0x40`

### Channel B
- pointers: `record+0x48`, `record+0x50`
- byte size: `record+0x58`

Runtime capture on the loaded almost-complete save:

```
record_count=425
pool_size=1055845

Channel A:
  payload_records=425
  payload_bytes=1046167
  exact Raven identity count=0
  decoded Raven entries=0

Channel B:
  payload_records=422
  payload_bytes=9678
  exact Raven identity count=0
  decoded Raven entries=0

known VikingFuneral Raven identity hits=0
```

Channel B contains valid custom-userdata carriers for ordinary WAD checkpoint state. In `Xpl200_Funeral` it contains the two known companion GameObject identities byte-for-byte, but not the Raven identity.

Channel A is a large separate per-WAD backing/state payload, but it is not directly a solved custom-userdata carrier stream and contains none of the 53 Raven serialized identities.

Therefore the blocker is no longer locating the WAD table or solving identity encoding. The blocker is:

**where does the authoritative Raven Lua checkpoint/custom-userdata stream live or transiently pass after/beside these staged WAD records?**

## Restore bridge already proven

Do not redo this proof:

- `0x465143` and `0x4651E2`: indirect `call [vtable+0x80]`
- LuaClient vtable `0xE04018`, `+0x80 = 0x5B2280`
- `0x5B22C3 -> 0x7E9550`
- related restore implementation `0x5AECAD -> 0x7E9550`

Restore machinery:

- restore root: `0x7E9550`
- carrier descriptor: `0x7E7660`
- record dispatch: `0x7E7B60`
- userdata path: `0x7E9190`
- custom-userdata restore callback: class slot `+0xC0`

## Your exact task

### 1. Recover semantics of the full 0xA8 WAD record

Trace all meaningful reads/writes of fields:

`+0x00..+0xA7`

but prioritise:

- `+0x20`
- `+0x24`
- `+0x28`
- `+0x30/+0x38/+0x40`
- `+0x48/+0x50/+0x58`
- `+0x60/+0x68/+0x70/+0x78`
- `+0x80/+0x84`
- `+0xA0/+0xA4`

Start with these concrete native functions:

- `0x82C820`
- `0x82CF00`
- `0x82D660`
- `0x82D760`
- `0x667230`
- `0x6687F0`
- `0x66BA10`
- `0x549481`
- `0x25CFD0`
- `0x23FAA0`

For each important field, identify:
- producer;
- consumer;
- lifetime;
- whether it is raw disk/staged data, engine object metadata, WAD asset data, Lua checkpoint data, or another class of state.

Do not merely dump xrefs. Recover dataflow and ownership.

### 2. Trace Channel A forward, not by scanning

For `record+0x30/+0x40`, identify exactly:

- who interprets its bytes;
- whether bytes are decompressed, deserialised, copied, indexed, or converted;
- destination buffers/objects;
- whether the payload eventually reaches a Lua client/context or restore dispatch;
- the smallest point after transformation where record boundaries remain known.

Channel A has `22505` bytes for `Xpl200_Funeral` in the current capture. Use that concrete record as the main fixture.

If Channel A is unrelated to Lua/custom-userdata state, prove that and stop treating it as a candidate.

### 3. Find the actual input that reaches LuaClient +0x80

Work backwards from:

`0x465143 / 0x4651E2 -> LuaClient vtable +0x80 -> 0x5B2280 -> 0x7E9550`

Recover the exact object and byte-buffer arguments at those two indirect calls.

Document:

- owner object/class;
- call-site conditions;
- buffer pointer;
- byte length;
- source of that buffer;
- whether it is per-WAD or global;
- whether nonresident WAD state is queued/stored before this call.

Then connect that buffer's provenance to either:
- a field in the 0xA8 staged record;
- another global per-WAD structure;
- or a separate global checkpoint stream.

### 4. Search by dataflow for the known Raven carrier, not broad memory

The VikingFuneral Raven identity is:

`01b0b227342530c24ea9652dba0717be98`

The two known companion identities in Channel B prove `Xpl200_Funeral` is the correct WAD record.

Find where the Raven's own persisted Lua subobject state diverges from those ordinary WAD checkpoint entries.

The desired boundary should still allow reuse of:

`tools/v0.10.5/decode-active-raven-subobject-state.py`

Do not implement a new speculative codec.

### 5. Runtime observer only if static proof gives one exact target

If static analysis narrows this to one transient buffer/structure, build the smallest read-only observer required to capture it.

Constraints:

- `ReadProcessMemory` / non-mutating observation only if possible;
- no `WriteProcessMemory`;
- no progression/save writes;
- no force-loading WADs;
- do not call unknown game functions;
- no broad process memory scans;
- bounds-check every pointer and size;
- pin the known executable SHA-256;
- archive evidence and push it;
- if user action is needed, provide exactly one PowerShell runner.

A targeted debugger/breakpoint observer is acceptable only if there is no RPM-visible retained buffer and the observation method is clearly non-mutating with respect to game/save/progression state. Prefer retained read-only structures.

### 6. Acceptance criteria

Best case:
- locate the exact global or per-WAD authoritative Raven stream;
- reuse solved decoder;
- recover exact `ravenKilled` states for catalogue IDs;
- Veithurgard exact fixture returns:
  - false
  - true
  - true
- independent RegionSummary remains 2/3;
- prove unloaded/nonresident Raven states are available for map-open reconstruction.

Useful partial success:
- prove exact provenance of the buffer that reaches `0x5B2280/0x7E9550`;
- identify one concrete retained/transient structure and exact observation point, with no broad searching left.

Not success:
- another xref dump;
- another blind memory scan;
- another physical-slot timestamp heuristic;
- aggregate-only Raven completion;
- guessing that absence means alive.

## Repo discipline

After each meaningful stage:

1. commit and push to `codex/all-ravens-release-candidate`;
2. archive evidence under `archive/field-logs/`;
3. update `archive/field-logs/local-handoffs/raven-authority-handoff-20260920.md`;
4. do not stage unrelated user files;
5. no force push;
6. no merge.

If you need the user to run a capture, stop after pushing the complete observer and runner, and give exactly one PowerShell command.

At the end, leave an explicit statement of:
- what is proven;
- what is ruled out;
- exact next unresolved boundary;
- whether the mod is ready to consume authoritative Raven state yet.
