# Raven scheduler -> allocator runtime binding

## Current result

`BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY`

`BLOCKED_EXACT_UNLOADED_STATE_ORACLE`

Runtime tooling is complete, but two clean-reload captures have not yet been
made. No persistent key pass is claimed from static evidence or from a repeated
token alone.

All addresses are locked to `GoW.exe` SHA256
`caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`.

## Exact target

- instance GUID: `95b9c644-4d47-9ac6-8207-b1829d02909b`
- WAD: `alf355_chiseldungeon.wad`
- WAD SHA256: `2e66a927426e83d4e7f2d6a17d5a3fd1387b1ddd415b7a5c43dc0d96fd7f5268`
- canonical record offset: `0x32E3C60`
- zero-based physical record index: `9633`
- final record ID: `44c6b995c69a474d82b107829c90029d`

The capture parser accepts target identity only when the unique complete raw
record or its unique complete 164-byte payload occurs in the pointer ancestry
captured from the scheduler event, descriptor source, descriptor, or WAD, and
the same event's WAD/scheduler ancestry contains exact
`alf355_chiseldungeon.wad` or `WAD_Alf355_ChiselDungeon` identity. Object name
and record-ID component hits are archived as supporting evidence but never mark
an event as the target.

## Observation points

The capture uses temporary one-byte software breakpoints in the live process:

- `0x859C0D`: canonical loader call. Worker frame supplies outer and inner list
  indices. The tool independently walks the global outer list and the selected
  outer node's inner list, checks the pointers against saved worker locals, and
  checks that `outer+0x40`, saved `WAD`, and loader `RDX` are identical.
- `0x4EF2B0`: allocator entry. The tool requires null `R8` (no slot hint), reads
  `WAD+0xC3C`, resolves the real registry pointer and its actual global table
  index, snapshots cursor/live count/capacity/bank, and reproduces the circular
  first-free scan including every tested slot.
- `0x4EF3BE`: fields-ready point after `GameObject+0x278`, `+0x280`, and `+0x284`
  have been stored. The tool reads those fields, decodes the tuple, computes the
  persisted token, and cross-checks registry ID and slot against allocator data.

Before attaching, both the on-disk executable hash and every instruction anchor
are checked. After ASLR module-base discovery, live bytes are checked again.
Each hit restores its original byte, single-steps the displaced instruction,
and reinserts the breakpoint. Other threads are suspended only during that one
instruction so no thread can pass a temporarily disarmed site. All bytes are
restored before debugger detach, including failure and interrupt paths. The EXE
on disk is never opened for writing.

## Comparison rule

Machine comparison has three outcomes:

1. deterministic/reconstructible only when both events have exact raw-record
   ancestry, tuple and allocator state match, and normalized allocation/free
   history is complete from fresh registry creation with the same causal hash;
2. repeatable but history-dependent when exact events and tokens match without
   that complete causal history;
3. different/unbound otherwise.

The capture records every allocator transition seen from attach, detects bank
changes between allocations (including unexplained frees), and recognizes the
case where a registry was absent at attach and its first allocation starts from
an empty bank, zero cursor, and zero live count. It still marks stable canonical
identities for preceding allocation events incomplete. Therefore it fails
closed even if the same token and normalized state-transition history appear
twice. A live capture can close the record-to-event and tuple edges and reveal
the smallest remaining identity/history edge without overstating what two
observations prove.

## Run command

From this worktree:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\v0.10.5\run-raven-scheduler-allocator-runtime-with-log.ps1
```

The wrapper starts the game, prints the two exact reload steps, captures all
registers and memory automatically, compares both runs, archives success or
failure, commits only its new archive directory, and pushes the branch. It does
not ask for manual address, register, memory, or log inspection.

## Safety boundary

The tooling never writes collectible/progression state, markers, or saves.
Normal game save activity is not suppressed, so the operator must not kill or
collect the Raven. This task does not inspect or claim the later frozen-save
`savedInfo.ravenKilled` binding; `BLOCKED_EXACT_UNLOADED_STATE_ORACLE` remains.
