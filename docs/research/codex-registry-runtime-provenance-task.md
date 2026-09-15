# Codex task: close GoW GameObject persistent-key blocker

Work on branch `codex/all-collectibles-production-research` in `Terru03/completionist-map-gow2018`.

## Goal

Close `BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY` by proving how God of War (2018) reconstructs the GameObject `(registry_id, slot)` tuple across reloads, with special focus on the runtime-populated 64-entry registry pointer table and the deterministic state/order feeding the slot allocator.

Do **not** weaken fail-closed behaviour. Do **not** mark the unloaded-state oracle as solved unless actual per-instance collectible completion semantics are proved. This task is static/read-only research unless a new runtime probe is absolutely necessary.

## Supported executable / local evidence

- `GoW.exe` expected SHA256: `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`
- Typical local exe: `G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe`
- SQLite research index: `.research-index\gow-caebcb027980.sqlite`
- Use the archived evidence already committed under `archive/field-logs/source-scans/`.
- Prefer exact narrow static data-flow over broad blind scans.

## Already proved — do not rediscover

### Save/restore token

The `__subobjs` GameObject key is Lua full userdata whose `+0x08` qword is the runtime token.

Token packing from GameObject:

```text
token =
  1
  | ((GameObject+0x280 & 0xFFFF) << 1)
  | (((GameObject+0x278 >> 3) & 1) << 17)
  | ((GameObject+0x284 & 0xFFFFF) << 18)
```

Inverse:

```text
registry_id = (token >> 1)  & 0xFFFF
flavor      = (token >> 17) & 1
slot        = (token >> 18) & 0xFFFFF
```

`0x5F96B0` serializes the same token qword; `0x5F95F0` decodes the qword and calls `0x4EF0B0(registry_id, slot, flavor)`.

Therefore there is **no hidden stable GUID substitution layer** in the serializer callback.

### Loader / GameObject fields

- GameObject `+0x278`: validity/flavor flags
- GameObject `+0x280`: registry ID
- GameObject `+0x284`: slot
- `0x856FAD`: loader reads level/WAD `+0xC3C` as registry ID
- `0x856FB7`: loader reads descriptor `+0x30` slot hint
- canonical builder paths examined so far pass slot hint `0xFFFFFFFF`; normal loads therefore use no-hint allocation.

### Dynamic allocation

`0x857329 -> 0x4EF4C0`.

`0x4EF4C0` is only a wrapper: it resolves the appropriate registry context, loads that context's `+0xC3C` registry ID, then tail-jumps to `0x4EF2B0`.

The real allocator `0x4EF2B0` has now been classified:

- registry `+0x20` = slot-bank pointer
- registry `+0x28` = circular first-free search cursor
- registry `+0x2C` = live-object count
- registry `+0x30` = capacity
- for no-hint allocation, it begins at `+0x28`, scans circularly, skips slot 0, takes the first null slot, writes the object, updates `+0x28` to the next search position, increments `+0x2C`, and stores registry/slot into GameObject `+0x280/+0x284`.

Exact useful sites:

- `0x4EF33F` cursor load
- `0x4EF346` capacity load
- `0x4EF34A` bank load
- `0x4EF35E` empty-slot test
- `0x4EF369` selected-slot store
- `0x4EF36D` cursor store
- `0x4EF371` live-count increment
- `0x4EF3A5` GameObject registry store
- `0x4EF3B8` GameObject slot store

### Registry pointer table

Latest archive: `archive/field-logs/source-scans/gow-registry-slot-state-20260915-123011/`

Global pointer table:

```text
0x22A98C0 .. 0x22A9AC0
64 entries × 8 bytes
```

All 64 entries are zero/non-file-backed in the PE image. Result classification:

```text
RUNTIME_INITIALIZED_REGISTRY_TABLE
```

The previous simple RIP-relative xref scan only surfaced two writes just before the table (`0x22A98A0`, `0x22A98A8`), so direct RIP xrefs are insufficient. Expect table population through a computed pointer/index, constructor loop, global container, or relocation/runtime init path.

### Registry ID producer clue

In `0x82CF00`:

```text
0x82D1FB / nearby path: registry ID is read from a record/object `+0x24`
0x82D203: stores that value to level/WAD `+0xC3C`
```

Another part of that owner writes a record `+0x28`; determine whether that structure participates in registry creation/assignment.

## Primary questions to answer

1. **Who populates `0x22A98C0..0x22A9AC0` at runtime?**
   - Find exact writer(s), including computed/indexed writes that a simple RIP-xref scan misses.
   - Identify constructor/destructor/reset function(s) for each registry object.

2. **How are registry fields initialized?**
   - Exact initial/reset values for `+0x20`, `+0x28`, `+0x2C`, `+0x30`.
   - Is cursor `+0x28` reset on registry/WAD creation, level reload, stream-in, or only process initialization?
   - Is the slot bank cleared/reset at the same time?

3. **How is `registry_id` assigned?**
   - Connect registry object/table index/registry-id field to the value copied into WAD/level `+0xC3C`.
   - Determine whether the ID is deterministic for a WAD/load context.

4. **What establishes canonical allocation order?**
   - Follow the normal WAD object-loading loop that calls `0x8566B0`/`0x856F50` and then no-hint allocation.
   - Determine whether object allocation order corresponds to a stable WAD record order / record index / file offset already available in catalogue extraction.

5. **Can a catalogue row deterministically produce `(registry_id, slot)` after reload?**
   - If yes, prove the formula/path with exact sites and at least one concrete Raven catalogue example.
   - If no, explicitly identify the runtime state that prevents an offline deterministic mapping and propose the narrowest alternative oracle strategy.

## Raven target for a concrete proof

Use an Odin's Raven row if possible. Example catalogue data in `catalogue/odins-ravens.json` includes:

- instance GUID `95b9c644-4d47-9ac6-8207-b1829d02909b`
- final record id `44c6b995c69a474d82b107829c90029d`
- override record id `44c6b995c69a474d82b107829c91029d`
- WAD `alf355_chiseldungeon.wad`
- final offset `0x32E3C60`
- object `goprecisionchallenge_raven_perch`
- progression field `ravenKilled`

Do **not** equate this GUID to the runtime token without a direct proven edge.

## Deliverables

Make concrete repo changes on this branch, not just a chat explanation:

1. Add or improve one or more research tools under `tools/v0.10.5/` that prove the relevant runtime registry initialization/order data-flow. Reuse existing PE/index helpers where possible.
2. Add a concise research document under `docs/research/` summarizing exact sites, structures, data-flow, what is proved, and what remains blocked.
3. Update status docs only if the proof actually changes blocker status.
4. If local `GoW.exe` execution of a read-only tracer is required, provide a self-logging PowerShell wrapper that archives its outputs and commits/pushes them exactly like the existing recent wrappers. Do not require manual copying of output.
5. Run all source-only tests/checks available to you. Do not launch the game or touch active saves unless absolutely unavoidable and explicitly documented.
6. Commit and push your work to `codex/all-collectibles-production-research`.

## Success criteria

Strong success:

```text
PASS_EXACT_GAMEOBJECT_PERSISTENT_KEY
```

Only claim that if a canonical catalogue/WAD instance can be proven to reconstruct the same `(registry_id, slot)` tuple after reload.

Otherwise leave it blocked and report the **single narrowest missing edge**. Do not manufacture a stable identity from assumptions.

Keep:

```text
BLOCKED_EXACT_UNLOADED_STATE_ORACLE
```

until actual per-instance collectible completion state semantics (e.g. the Raven's `ravenKilled`) are bound to the restored object/save state.