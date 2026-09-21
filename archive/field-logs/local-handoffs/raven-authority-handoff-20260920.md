# Completionist Map v0.10.5 - Raven authority handoff

**Date:** 2026-09-20  
**Branch:** `codex/all-ravens-release-candidate`  
**Repo:** `Terru03/completionist-map-gow2018`  
**Local clone:** `C:\Users\david\Documents\GitHub\completionist-map-gow2018-all-ravens-release-candidate`  
**Purpose:** Prevent rerunning solved or already-executed Raven persistence probes. Continue only from the remaining authority/event-bridge boundary described at the end.

## Non-negotiable runtime goal

The Raven release candidate must satisfy all of these without writing save/progression state:

- fresh save: all 53 Ravens visible;
- old/almost-complete save: only surviving Ravens visible;
- killing a Raven removes its marker immediately;
- opening/reopening the map reconstructs the exact killed Raven set from authoritative checkpoint/save state;
- preserve the already-working realm, caption, map-art, compass and marker lifecycle fixes;
- absolutely no save/progression writes.

Keep this work isolated on `codex/all-ravens-release-candidate`.

---

# STOP: tests/probes already completed in this chat

Do **not** rerun anything in this section unless a later code change specifically invalidates its evidence.

## 1. Lua restore pre-dispatch helper trace - DONE

**Evidence commit:** `b2a8f737de58185279498be64173ccb63c8251f1`  
**Evidence:** `archive/field-logs/source-scans/lua-restore-pre-dispatch-helpers-20260920-110309/`

**Tooling:**
- `tools/v0.10.5/trace-lua-restore-pre-dispatch-helpers.py`
- runner from commit `e2435e6dbd70...`

### Proven
- `0x5A4370` belongs to a restore/materialisation path and manipulates Lua-side subobject/chunk state.
- It writes `client+0x68` from owner/context lookup and temporarily stages the owner/context pointer in `client+0x70`.
- It references `_SUBOBJECT_CHUNKS`, `_SUBOBJECTS`, `__index`.
- The earlier assumption that `+0x70` was always a serialized blob was too broad.

### Important correction
This trace led to a candidate `0x5A4240`, but that candidate was later disproven as the LuaClient restore-buffer finaliser. Do not revisit it as though it were unresolved.

---

## 2. Contiguous `0x5A4240` finaliser trace - DONE, FALSE LEAD CLOSED

**Tool commits:**
- `08665402d6f686681bfec66e402e34f7dae849ce`
- `5c06fe1a03f4f592f01bc555bae7dd073035cb34`

**Evidence commit:** `cc979a71a43e925b7547c33f4157096204ee2a9f`  
**Evidence:** `archive/field-logs/source-scans/lua-restore-finalizer-contiguous-20260920-110744/`

### Result
The previous unwind/function boundary was wrong, but after tracing contiguous control flow the conclusion was:

- `0x4652B0 -> 0x5A4370 / 0x5A4240` is **not** the LuaClient serialized restore-buffer path we need.
- `0x5A4240` registers an object into an owner-side list and sets an object field around `+0x7C`; its `+0x70` is merely an offset collision with LuaClient.
- Therefore this path is **closed as a false lead**.

**Do not rerun this trace.**

---

## 3. Full live registry-238 Raven sweep attempt #1 - DONE, validation assumption disproved

**Tool commits:**
- `f58b6be4e178259bff5dc53262f462f7816f7832`
- `b9adac710cd1900fa7d53b488785b27e42da0cab`

**Evidence commit:** `6dfb7b81877fe7387d30397b6d7c5a672951b9a8`  
**Evidence:** `archive/field-logs/runtime-captures/all-raven-gameobject-identities-readonly-20260920-112945/`

### Failure
The sweep originally required every Raven override to satisfy:

`override + 0xAC == final_record_id`

This failed on:
`raven_95b9c6444d479ac68207b1829d02909b`.

### Conclusion
The `override+0xAC` relation is true for the proven VikingFuneral Raven but is **not a universal WAD layout invariant**.

### Fix
Commit `61a1636b6dd3f7bf54b5595846c0f43c08065b29` relaxed that assumption. The authoritative static identity source remains the final WAD record header.

**Do not restore the old +0xAC assumption.**

---

## 4. Full live registry-238 Raven sweep attempt #2 - DONE, live-registry strategy disproved for unloaded Ravens

**Evidence commit:** `09b1a0c4725df84d679732f962661689ffb69e5e`  
**Evidence:** `archive/field-logs/runtime-captures/all-raven-gameobject-identities-readonly-20260920-113151/`

### Failure
`RuntimeError: expected one registry 238, found 0`

### Conclusion
Registry 238 is area/load dependent. It was present in VikingFuneral while those relevant GameObjects were loaded, but it is not globally available from an arbitrary current area.

Therefore:

- a global live registry-238 sweep cannot solve all unloaded Ravens;
- do **not** ask the user to travel through all Raven WADs;
- do **not** rerun this registry sweep from random locations expecting 53 Ravens.

---

## 5. Static Raven prototype identity resolution - DONE

**Tool commits:**
- `c2608ecc16d431faaa0777118457e03a4558697e`
- `326dbdfd056da27442e5247e00032fd46473afcb`

**Evidence commit:** `2366fdcc23acccfe2a31a2aa981be8e62176a365`  
**Evidence:** `archive/field-logs/source-scans/raven-prototype-identities-static-20260920-113536/`

### Major result
All 53 Ravens reduce to **six catalogue prototype IDs**, and those six reduce to only **two runtime prototype/object identity elements**:

#### Perch/hop family
Prototype IDs:
- `408280c2887ca5d7cba94feea56888d0`
- `f4f22e4546b2194891ad7f9a7c5b6dc4`

Runtime prototype/object identity element:
`805b030bf339564cb157837c52906465`

#### Hover family
Prototype IDs:
- `0c397df6a1dcb23d8859241c3c713ac1`
- `3a519f6b5782fea73e617a71a7c726ce`
- `bd01be1157e065d6910e0c26c6fae6ab`
- `cbd08dc1fea41249375bb6b2fa795111`

Runtime prototype/object identity element:
`50dafefd65605b41a2aed011a5f4ce22`

### Proven scene-vector transformation
For a Raven catalogue row:

1. take `source.transform_chain`;
2. reverse it;
3. for every 16-byte record ID, decrement byte index 12 by one modulo 256;
4. append the family prototype/object identity element above;
5. hash all identity bytes with the native `0x401` rolling hash.

This exactly reconstructs the known VikingFuneral Raven object hash:

`0x98BE1707BA2D65A9`

This is solved. **Do not repeat prototype-family probing.**

---

## 6. All 53 serialized Raven GameObject identities - SOLVED

**Generator commits:**
- `6a74a8520f2f702c635d21c2892d8b011c4cb20a`
- `9518443e879d8a42ace8659c5b33180e559a0ced`

**Generated catalogue commit:** `87312c353be55ce2682d16065f78c0a7383c15b4`

**Canonical output:**
`catalogue/odins-ravens-gameobject-identities.json`

### Result
- 53 catalogue Ravens
- 53 unique serialized GameObject object hashes
- 53 unique serialized flag-1 GameObject identities
- registry hash:
  `0x4EC230253427B2B0`

### Hard validation
Known VikingFuneral Raven:

- catalogue ID: `raven_642d0d164af0a5d4076e77933c549a5d`
- object hash: `0x98BE1707BA2D65A9`
- serialized 17-byte GameObject payload:
  `01b0b227342530c24ea9652dba0717be98`

This exactly matches the previously solved save-side GameObject codec evidence.

**The catalogue Raven -> serialized GameObject identity problem is CLOSED. Do not redo it.**

---

## 7. 53-Raven active-save ring authority probe attempts - DONE

### Probe implementation
**Commit:** `650f8bcd4cc6...`  
It binds the proven custom-userdata carrier parser to:
`catalogue/odins-ravens-gameobject-identities.json`.

### First failure
**Evidence commit:** `d6fd085f7583...`  
The scanner overflowed Python recursion in `gow-custom-userdata-carrier-scan.py::metadata_ends`.

### Fix
**Commit:** `8332da2b2cf6...`  
Metadata scanning changed to iterative/bounded state traversal.

### Second failure
**Evidence commit:** `4f56126c80b789fd51877d3da6562244375aa7f8`  
A second recursion overflow remained in `gow-custom-userdata-carrier.py::infer_metadata`.

### Fix
**Commit:** `8e50c33395bf1f306c099192da08f5f0d78de81b`  
Carrier metadata inference also changed to iterative traversal.

### Successful authority scan
**Evidence commit:** `3e6a98258ebd8948b2c167a7ed6e6d223e3f4f2b`  
**Timestamp:** `20260920-124126`

Result line:

`ACTIVE_SAVE_RAVEN_RING_AUTHORITY_PROBE_COMPLETE occupied=20 authoritative=0 killed=0`

Safety:
- active save opened read-only;
- source hash unchanged;
- save written = false;
- progression written = false;
- game process opened = false.

### Important slot evidence
The probe correctly decoded real historical Raven kill records:

- slot 18: one killed Raven
  - `raven_642d0d164af0a5d4076e77933c549a5d`
- slot 19: three killed Raven identities
  - `raven_642d0d164af0a5d4076e77933c549a5d`
  - `raven_c945cb53465b58decfcbd4a221cb5326`
  - `raven_e32f7bab42fd7298890f6aa56a734562`

The timestamp-consensus logic selected slot 0 as latest:
- slot 0 timestamp: `2026-09-20T11:35:53Z`
- slot 0 decoded killed Raven count: 0.

### Interpretation
This proves the **53-way GameObject matching and Raven kill-record decoding work against real save-ring data**.

It does **not** yet prove that selecting the newest disk ring slot is sufficient as the live gameplay authority. The almost-done runtime state still needs a bridge at load/restore time.

**Do not rerun the 53-Raven active-save ring scan just to re-prove parsing.**

---

## 8. Native 17/21-byte GameObject reference decoding - DONE

**Fix commits:**
- `60f7ae78f81d66543ffa74a4a8c70c8210a386d8`
- `1dd1f4d2798ac63883d3a9a2f6ba20c4e17e782f`

### Result
The Raven authority graph/parser now handles the native `0x5491A0` GameObject reference forms, including extended 17/21-byte representations.

The GameObject codec itself was solved before this chat and must not be redone.

---

## 9. Raven runtime authority capability probe - DONE

**Probe commits:**
- `ced6cad8b0d2e7b7bdcf1268c6aa072f16881bdf`
- `27af4ed54897b01e635fdd9db7f1312f14c02ab9`

**Evidence commit:** `3d17ea1ccc3b63bdf5bc18b303944a5045922f0c`  
**Evidence timestamp:** `20260920-131711`

Result:
`RAVEN_AUTHORITY_CAPABILITIES_CAPTURED`

### Lua sandbox capabilities
Observed:

- `io=nil`
- `os=nil`
- `io.open=false`
- `require` exists
- `require('zlib')` fails
- `require('deflate')` fails
- `require('inflate')` fails
- no useful global zlib
- no direct Lua-side file-read route found
- no progression/save/marker/streaming writes made by probe.

### Runtime pickle evidence
The probe can traverse `__PickleTable` and observe real Raven persisted state for loaded/retained Raven objects.

Examples observed with `killed=true`:
- `WAD_Xpl875_DungeonForestLH`
- `WAD_Xpl850_DungeonForest`
- `WAD_Xpl200_Funeral`

It found Raven rows such as:
- `precisionchallenge_ravenhover`
- `precision_challenge_raven_perch`

### Limitation
The Lua object `__identity` exposed only generic:
`Class GameObject`

Hex:
`436c6173732047616d654f626a656374`

So Lua's exposed identity metamethod is **not** the unique native/save GameObject identity.

### Meaning
Runtime Lua can see authoritative `ravenKilled` booleans for objects represented in `__PickleTable`, but:

- Lua cannot directly read the save file through normal `io`;
- the exposed `__identity` is generic, not a catalogue key;
- therefore the remaining design problem is an engine/load-event authority bridge, not identity derivation.

**Do not repeat this capability probe.**

---

# Existing runtime behaviour that was already working before these probes

Do not regress this while solving unloaded persistence:

- real Raven + custom twin visible initially;
- Raven map/compass artwork works;
- exact marker tracking works;
- same-marker second click removes;
- stock dock remains native;
- killed Raven clears immediately with map closed;
- restore an uncollected Raven makes it return;
- recollect clears it again;
- no crash;
- loaded Raven script reads native `ravenKilled`;
- `_G.CompletionistMapV105PublishRavenState(...)` and persisted-bootstrap hooks already exist;
- no progression writes.

Relevant runtime files:
- `tools/v0.10.5/all-ravens-map-runtime.lua`
- `tools/v0.10.5/all-ravens-gameplay-events.lua`
- `tools/v0.10.5/build-all-ravens-release-candidate.py`

---

# Current exact boundary

The following are now solved:

1. all 53 static Raven positions/realm/region/catalogue IDs;
2. immediate loaded-instance `ravenKilled` handling;
3. custom map/compass marker lifecycle;
4. custom-userdata carrier grammar;
5. GameObject save-reference codec;
6. Raven catalogue -> serialized GameObject identity for all 53;
7. read-only decoding of historical `ravenKilled` records in real save-ring slots;
8. Lua runtime visibility of `ravenKilled` entries through `__PickleTable`.

The remaining problem is:

> **How to obtain/rebuild the exact authoritative killed-Raven set at save/load/checkpoint restoration time for unloaded Ravens, inside the mod runtime, without save/progression writes.**

The solution should bridge authoritative load/restore state into:
`_G.CompletionistMapV105ApplyPersistedRavenKills(catalogueIds, source)`

It should not add any save mutation.

---

# NEXT STEP - NOT YET RUN

**Current branch head before this handoff was created:** `e948ab1522e25f59268267079faa08a33706bc98`

That commit adds:

`tools/v0.10.5/scan-save-load-event-bridges-and-push.ps1`

This is the **next probe**.

It is a static source scan of the installed Lua source tree for save/load event bridges including:

- `EVT_LoadSaveData`
- `EVT_LoadSaveFile_Done`
- `EVT_ManualSaveComplete`
- `EVT_AutoSave`
- `EngineEvents`
- `ManualSaveComplete`
- `LoadSaveData`
- `LoadSaveFile_Done`

It has **not yet been executed** in the work represented by this handoff.

## Recommended next action

Run only the save/load event bridge source scan, inspect its evidence, and use that to locate a native/runtime event where the authoritative restored pickle/checkpoint state is available.

Do **not** start by rerunning:
- `trace-lua-restore-finalizer-contiguous-and-push.ps1`
- `capture-all-raven-gameobject-identities-readonly-and-push.ps1`
- `resolve-raven-prototype-identities-static-and-push.ps1`
- the 53-Raven ring authority scan;
- the Raven runtime capability capture.

Those questions have already been answered above.

---

# Safety invariant

All work in this handoff was designed around:

- no save writes;
- no progression writes;
- no quest writes;
- no process memory writes in read-only memory probes;
- no marker-state writes in authority capability probes;
- preserve the user's real save.

Any future implementation must maintain that invariant.

---

# Addendum 2026-09-20 17:21 - save/load event route CLOSED

Two read-only runtime probes tested the remaining engine event hypothesis after the handoff was written.

## Direct core.thunk event hooks - no delivery

Evidence commit: `21d40cf1cbdcb28a49bd57f2c5f6fe83b9f3c9ea`  
Evidence: `archive/field-logs/runtime-captures/save-load-event-arguments-20260920-171456/`

The early probe successfully installed hooks for:
- `EVT_LoadSaveData`
- `EVT_LoadSaveFile_Done`
- `EVT_AutoSave`
- `EVT_ManualSaveComplete`

During a main-menu load of the almost-done save, all four produced zero events through `core.thunk`.

## ui/fsm.lua HandleEvent dispatcher - no delivery

Evidence commit: `9271144711aca38bf29af2149e121e1cefc14492`  
Evidence: `archive/field-logs/runtime-captures/save-load-event-arguments-20260920-171940/`

The probe was injected directly into `ui/fsm.lua::HandleEvent(name, ...)` and loaded successfully. During another main-menu load of the almost-done save:

- target_event_count=0
- load_save_data_count=0
- load_save_file_done_count=0
- auto_save_count=0
- manual_save_complete_count=0

The temporary `mods/lua/.../fsm.lua` override was removed and verified absent afterward.

### Conclusion

The `EngineEvents` names are present in `_G.EngineEvents`, but these load/save events are not delivered through either tested Lua hook layer during the actual save load. **Close the Lua engine-event bridge route. Do not repeat variants of these probes unless new native evidence proves a different dispatch mechanism.**

### Remaining productive direction

Use the existing reusable static index to identify the native save/load manager / current restored-save owner and trace the in-memory authority path. A native helper is only worth considering if the installed mod stack exposes a practical extension point; do not assume `package.loadlib` is viable because that route already failed.

---

# Addendum 2026-09-20 19:27 - current save slot semantics

Evidence commit: `53bf3b1d36b1ea8f67767bee80ed38a10b7a0b7a`  
Evidence: `archive/field-logs/runtime-captures/current-save-slot-20260920-192423/`

The shipped save utility uses `local UI = game.UI` and performs:

```lua
local slotIndex = GetSaveSlotIndex(saveData)
UI.SetCurrentSlot(slotIndex)
UI.LoadSaveGame()
```

A read-only runtime probe confirmed `game.UI.GetCurrentSlot` and `game.UI.IsSlotValid` are callable. During a main-menu load of the almost-done save, the three observed UI-context initializations returned:

- before load: `slot=-1`, `IsSlotValid(-1)=false`
- after load: `slot=-1`, `IsSlotValid(-1)=true`
- gameplay context: `slot=-1`, `IsSlotValid(-1)=true`

Conclusion: after the load transition, `-1` is the special current/checkpoint slot. It is **not** the physical save-ring slot index needed to bind the authoritative Raven carrier. Do not use `GetCurrentSlot()==-1` as a ring selector.

Next target: trace the real index between `SetCurrentSlot(realIndex)` and the native `LoadedIntoSaveSlot` path. Static anchors are `0x533E30` and its sole external caller `0x7698BF`, plus the native handlers registered for `GetCurrentSlot` / `SetCurrentSlot`.

---

# Addendum 2026-09-20 20:28 - physical slot native loader

Evidence commit: `f449a16ef96c3496428b71374772f60194146881`  
Evidence: `archive/field-logs/source-scans/physical-slot-to-restore-20260920-202704/`

The native selected-slot path is now concrete:

```text
UI.SetCurrentSlot(realSlot)
  -> handler 0x7690E0
  -> stores Lua arg #1 at global 0x11BDB5C

UI.LoadSaveGame()
  -> handler 0x7691D0
  -> loads 0x11BDB5C
  -> calls 0x66CB30(realSlot, true)
```

Inside `0x66CB30`:

- requested slot is normalized to `0..9` or `-1`;
- normalized value is stored at global **`0x1078F4C`**;
- load-state globals include `0x2D3755E` and `0x2D375C6`;
- the current static function index incorrectly ends the routine at `0x66CB68`, but the real control flow branches forward to **`0x66CD09`**.

Therefore the failed shortest-path search from `0x66CB30` to the known restore/carrier functions is not evidence of separation; the index boundary truncates the real load routine. Next step is raw contiguous disassembly through the forward branch plus xrefs to `0x1078F4C` and the public slot globals.

---

# Addendum 2026-09-20 20:52 - contiguous physical-slot loader resolved

Evidence commit: `555e51a62d78eed86a88f4cc6bf0d63a8823f340`  
Evidence: `archive/field-logs/source-scans/save-slot-contiguous-control-flow-20260920-205117/`

The raw contiguous disassembly resolves the misleading function-boundary issue around `0x66CB30`.

## Confirmed loader behavior

`0x66CB30` really continues through the forward branches and returns at `0x66CD0E`. The indexed fragments between `0x66CB30` and `0x66CD09` are one contiguous logical load-slot routine.

It performs:

- normalize requested physical slot to `0..9` or `-1`;
- store normalized slot in **`0x1078F4C`**;
- clear/reset load-state byte **`0x2D3755E`**;
- consult load-state flag **`0x2D375C6`**;
- for valid slot entries, copy the selected per-slot metadata block from base **`0x4FE8210`** with stride **`0x148`** into active globals around `0x22C67xx`;
- call `0x661A60` to bind/copy slot-backed regions;
- optionally call `0x681CA0` before returning when the relevant load mode is active.

Important correction to the prior handoff: **`0x66CD09` is only the epilogue/return path**, not a separate downstream decode routine.

## Native physical-slot authority global

Global **`0x1078F4C`** is now the strongest native physical-slot state anchor. It has 9 indexed RIP references:

- `0x6628B7` in `0x6626B0-0x662A87`
- `0x66AF4C` in `0x66ABD0-0x66B048`
- `0x66B888` in `0x66B650-0x66BA04`
- `0x66C09D` in `0x66C080-0x66C22C`
- `0x66C256` in `0x66C240-0x66C38C`
- `0x66C85F` in `0x66C840-0x66C86F`
- `0x66CB5C` in `0x66CB30-0x66CB68`
- `0x680A0D` in `0x67FE20-0x680EFC`
- `0x768BED` in `0x768BB0-0x768BFD`

The public UI selected-slot global `0x11BDB5C` only has 3 refs and is the pre-load UI selection. `0x1078F4C` is the better candidate for the native loaded physical slot.

Next step: inspect every `0x1078F4C` reference function, especially the large `0x67FE20-0x680EFC` owner around `0x680A0D`, and trace those functions toward the known save/restore/carrier stack. Do not redo UI getter/event/root probes.

---

# Addendum 2026-09-20 21:09 - physical slot lifetime and active-slot handoff

Evidence commit: `a78d60079b04e0b88c8913f83f8417b50626e4d4`  
Evidence: `archive/field-logs/source-scans/native-load-slot-global-20260920-210702/`

All 9 native xrefs to physical-slot global **`0x1078F4C`** were traced.

## Important lifecycle result

The large state-transition owner `0x67FE20-0x680EFC` accesses `0x1078F4C` at `0x680A0D` and explicitly writes **`-1`** after the game has handled `OnStartGameFromThisLevel` and associated load-transition state.

Relevant sequence around `0x680A06-0x680A17`:

- reset related slot/checkpoint globals (`0x1078EBC`, `0x1078F48`, `0x1078F78`);
- clear load-state byte `0x2D3755E`;
- write **`0xFFFFFFFF` to `0x1078F4C`**;
- mark the post-load state via adjacent flags.

Conclusion: **`0x1078F4C` is authoritative only during the load transition and is intentionally discarded once gameplay takes over.** It cannot be the long-lived runtime authority source by itself.

## Active slot-backed state before reset

Before the slot is reset, the save subsystem copies/binds the selected slot's `0x148` metadata entry from per-slot base `0x4FE8210` into active globals and slot-backed regions, including:

- `0x22C67D0`
- `0x22C67B0`
- `0x22C67B8`
- `0x22C6148`
- related `0x22C67xx` globals

The initialization/selection owner `0x6626B0` uses `0x1078F4C` to copy the chosen `0x148` slot metadata into the live active block and then invokes `0x661C00`, `0x661CC0`, `0x661BC0`, and `0x66C080`.

## Checkpoint file path owner

`0x66ABD0-0x66B048` is confirmed inside the same subsystem and constructs/opens:

```text
checkpoint.SGA
/data
%s/%s%s
```

It calls file/stream helpers around `0x9C4CC0`, `0x9C4510`, `0x9C44B0`, and `0x9C5840`, then continues through save/checkpoint processing helpers.

Next target: trace the active globals/buffers copied from the selected physical slot—especially `0x22C67D0`, `0x22C67B0`, and `0x22C67B8`—and the `checkpoint.SGA` read path toward the already-solved restore/carrier routines. The objective is to find a long-lived in-memory loaded-checkpoint buffer or decoded authority structure that survives after `0x1078F4C` is reset.

---

# Addendum 2026-09-20 21:31 - active save/checkpoint buffer layout

Evidence commit: `86e265587a2fab09a2d93bef2f57f79e88564468`  
Evidence: `archive/field-logs/source-scans/active-save-buffers-20260920-212713/`

The active save/checkpoint workspace is now mapped by native xrefs.

## Live buffers and descriptors

- **`0x22C67A8`**: 4 MiB allocation pointer.
- **`0x22C6788`**: 16-byte descriptor wrapping the 4 MiB allocation; fields include base pointer and size `0x400000`.
- **`0x22C6928`**: `0x20000` companion buffer.
- **`0x22C67B8`**: `0x10000` companion buffer.
- **`0x22C67B0`**: another `0x20000` companion buffer.
- **`0x22C67D0`**: active `0x148` slot metadata block.
- **`0x22C6148`** and related `0x22C67xx` globals are part of the active slot-backed region set.

Allocation/free helpers:

- `0x661F40` allocates the 4 MiB buffer and descriptor.
- `0x661EB0` frees/clears them.
- `0x661D18` consumes the descriptor as a bounded byte reader/writer using descriptor fields `base`, `size`, and cursor.

## Slot binding

`0x66239D` is a concrete active-slot binding routine. It:

- selects/copies the `0x148` metadata entry;
- invokes `0x661C00` for slot bookkeeping;
- invokes `0x661CC0` repeatedly to bind slot-backed regions into:
  - `0x22C6148`,
  - `0x22C67B8`,
  - `0x22C67B0`;
- calls `0x661BC0` after binding.

The offsets use the known per-slot stride `0x1998C8`.

## Checkpoint path relationship

`0x66ABD0`, which explicitly constructs/opens `checkpoint.SGA`, directly references the active `0x10000` and `0x20000` buffers (`0x22C67B8`, `0x22C67B0`) plus `0x22C6148`.

This strongly ties those smaller live buffers to checkpoint-file processing rather than UI-only state.

## 4 MiB workspace interpretation

The 4 MiB buffer/descriptor is a generic active serialization workspace. It is allocated/freed centrally and used by bounded stream helpers, but direct indexed call paths from its xref owners to the known Raven restore/carrier stack were not found. This suggests the final handoff into restore is through an indirect/vtable/callback dispatch, not a simple direct call edge.

Next target: bridge the `checkpoint.SGA` processing side to the known restore side from both directions. Analyze forward descendants of checkpoint readers/binders and reverse ancestors of `0x5AEC9E`, `0x5B2280`, and `0x7E9550`; intersect direct functions, shared data globals, and indirect-call tables. Also inspect central helpers `0x661CC0`, `0x661E30`, and the checkpoint processing functions reached from `0x66ABD0`.

---

# Addendum 2026-09-20 21:34 - first checkpoint/restore static intersection

Evidence commit: `67c423eb7461cabef7defe53cdcaf4d7805579a0`  
Evidence: `archive/field-logs/source-scans/checkpoint-restore-bridge-20260920-213242/`

A two-sided graph/data analysis was run from the checkpoint/save subsystem toward the known Raven restore stack.

## Direct-call graph

Within depth 7:

- checkpoint-side forward reachable functions: **571**
- restore-side reverse reachable functions: **6**
- common direct-call functions: **0**

This confirms the missing handoff is not represented as an ordinary direct-call edge in the current index.

## First concrete static intersection

Two shared native `.rdata` targets are referenced from both sides:

### `0xD9E6B0`

Checkpoint-side references include:

- `0x5A3CE0`
- `0x782FE0`
- `0x9E44B0`
- `0x9E8190`
- `0x9ECF00`
- `0x9ED450`
- `0x9ED520`

Restore-side references include:

- `0x5B2280`
- `0x7E7660`
- `0x7E9550`

### `0xD9E4E8`

Checkpoint-side references include:

- `0x9EC6C0`
- `0x9ECE90`
- `0x9ECF00`
- `0x9EDFC0`

Restore-side references include:

- `0x7E7660`
- `0x7E9550`

## Strongest bridge candidate

**`0x9ECF00` is especially important:**

- it is reachable from the checkpoint/save side;
- it references **both** shared `.rdata` objects;
- `0x7E9550` directly calls `0x9ECF00` at `0x7E99C9`.

This is the first function/object family statically tied to both the loaded checkpoint path and the already-solved Raven carrier restore path.

The checkpoint side also contains indirect dispatches at `0x66ABD0`, `0x669300`, and `0x669B00`, while `0x7E9550` has indirect calls at `0x7E984F` and `0x7E995E`. These may use the shared `.rdata` objects as type/vtable/descriptor tables.

Next target: classify `0xD9E6B0` and `0xD9E4E8` (vtable/type/descriptor/dispatch structure), fully analyze `0x9ECF00` and its callers/callees, and resolve whether the checkpoint-side indirect dispatch reaches the same implementation family used by `0x7E9550`.

---

# Addendum 2026-09-20 21:44 - shared-rdata bridge lead CLOSED

Evidence commit: `ccaf07dde92cd5d1f9887382879a1d960554338f`  
Evidence: `archive/field-logs/source-scans/shared-rdata-restore-bridge-20260920-214151/`

The two shared `.rdata` targets previously seen from both checkpoint-side and restore-side functions are **not save/restore bridge descriptors**. They are generic Lua-runtime constants and therefore the overlap is incidental.

## `0xD9E6B0`

The bytes beginning at `0xD9E6C0` are the canonical 256-entry ceiling-log2 lookup pattern:

```text
0,1,2,2,3,3,3,3,4...5...6...7...8...
```

This is a generic Lua runtime helper table used broadly throughout the VM. It has 1,619 exact xrefs, confirming it is not a save-specific object.

## `0xD9E4E8`

This region is adjacent to the embedded Lua 5.2.3 identification string beginning at `0xD9E510`:

```text
$LuaVersion: Lua 5.2.3 ...
```

It likewise belongs to Lua runtime static data, not checkpoint authority.

## `0x9ECF00`

`0x9ECF00` is therefore a Lua VM helper, not a checkpoint/save bridge. Its presence on both sides reflects the fact that both checkpoint loading and carrier restoration manipulate Lua values/tables.

**Closed lead:** do not use `0xD9E6B0`, `0xD9E4E8`, or `0x9ECF00` as evidence of a save/checkpoint authority bridge.

## Next direction

Return to the proven checkpoint callback path rather than generic Lua internals. Static anchors already established:

- per-subobject restore: `0x5AD4A0`
- `__subobjs` lookup: `0x5AD51F`
- packed GameObject token push: `0x5AD597`
- `OnRestoreCheckpoint(level, subobject, savedInfo)`: `0x5AD5F3`
- save-side symmetry around `0x174B78` / `0x174B98`
- helper `0x5A3CE0` references `_SUBOBJECTS` and invokes Lua dispatch indirectly.

Next target: resolve exactly how the active checkpoint/save buffers are transformed into the `__subobjs` table consumed by `0x5AD4A0`, and whether the table/root remains reachable after load. Focus on the direct callers/ancestors of `0x5AD4A0` and `0x5A3CE0`, plus their shared non-Lua-runtime globals. Do not revisit generic Lua `.rdata` tables.

---

# Addendum 2026-09-20 21:5x - durable unloaded-resource Lua backing cache

This addendum consolidates already-existing Raven-branch static evidence that became the strongest authority route after the generic Lua-rdata bridge was closed. No new gameplay probe is required for these conclusions.

Primary existing evidence:

- `archive/field-logs/source-scans/lua-client-backing-transfer-20260920-103728/`
- `archive/field-logs/source-scans/lua-cached-backing-materialization-20260920-104039/`
- `archive/field-logs/source-scans/luaclient-slot11-restore-materialisation-20260920-105211/`
- `archive/field-logs/source-scans/lua-restore-pre-dispatch-helpers-20260920-110309/`
- `archive/field-logs/source-scans/softpickle-state-owner-constructor-20260920-100713/`

## Class identities

RTTI proves:

- vtable `0xE03F18` = **LuaLevelClient** (`.?AVLuaLevelClient@@`)
- vtable `0xE04018` = **LuaClient** (`.?AVLuaClient@@`)

## LuaLevelClient checkpoint/backing fields

Existing analyzers establish:

- **`LuaLevelClient+0x68` = durable per-resource backing-state node**
- `LuaLevelClient+0x70` = transient normal-pickle blob
- `LuaLevelClient+0x78` = transient soft-pickle blob
- `0x5A6DD0` constructor receives the durable backing node in R9 and stores it at `+0x68`
- `0x5A6C10` consumes `+0x70/+0x78` length-prefixed blobs (`u32 size` + payload), invokes virtual restore methods, frees the blobs through the backing allocator, and clears the transient pointers
- `0x5A6270` performs the inverse transfer back into durable backing storage

Thus the per-WAD Lua `__PickleTable/__SoftPickleTable` roots are transient materializations, while the native backing node is the durable layer above them.

## _SUBOBJECT_CHUNKS staging

`0x5A4370` references both **`_SUBOBJECT_CHUNKS`** and **`_SUBOBJECTS`** as real Lua globals during pre-restore staging. It installs the incoming transient chunk at client `+0x70` and materializes the Lua tables used later by the per-subobject restore callback path.

This explains why runtime Unpickle probes only see the currently materialized WAD: they observe the transient table after one durable backing entry has been materialized.

## Critical native cache: LuaContext+0x178

On client/resource detach, `0x46538B..0x4653FC` does:

```text
rdi = client
rbx = [client+0x68]          ; durable backing node
... detach/destroy client ...
rcx = LuaContext + 0x178     ; cache list head
rax = [rcx+8]
[rcx+8] = rbx
[rbx+8] = rax
[rbx] = rcx
[rax] = rbx
```

Therefore **`LuaContext+0x178` is a doubly-linked-list head containing durable backing nodes for detached/unloaded resources**. It is not a single “last resource” pointer.

This is the first native structure found that can plausibly retain state for many unloaded WADs simultaneously.

## Cache lookup on resource/client creation

`0x4654A0..0x4658BC` searches that list when a client is created:

```text
resource_key = [[r8+0x30]+0x18]
head = LuaContext + 0x178
for node in list:
    if [node+0x18] == resource_key:
        unlink node
        pass node as R9 to 0x5A6DD0
```

Thus backing-node **`+0x18` is the resource key** used to associate durable state with a resource/WAD. A matched node is unlinked from the cache and reattached to the new LuaLevelClient.

Known/likely node fields from existing code:

- `+0x00/+0x08`: doubly-linked-list links
- `+0x10`: used as a scalar/count during backing transfer (`0x5A7776`)
- **`+0x18`: resource key**
- `+0x28`: allocator/backing owner used to allocate/free transient blobs

## Architectural conclusion

The WAD-scoped Lua roots are not the global authority, but the engine retains their durable serialized state in a **multi-entry native LuaContext cache for unloaded resources**. This is now the strongest route to all-53 Raven historical state without reading `game.sav` from Lua or loading every WAD.

Next target: statically recover the backing-node structure and resource-key identity well enough to enumerate Raven-bearing cached resources and locate their serialized normal/soft checkpoint payloads. Specifically resolve:

1. the type/value behind `[[r8+0x30]+0x18]` used as the cache key;
2. all backing-node field accesses around `+0x10/+0x18/+0x20/+0x28` and beyond;
3. which fields own the durable normal/soft serialized chunks;
4. whether an existing Lua-visible/native callback path can expose these cached chunks read-only at runtime.

Do not repeat broad Unpickle-root, `__prevunpickle`, save-event, registry-sweep, or generic Lua-runtime probes.

---

# Addendum 2026-09-20 21:58 - backing-cache capture output handling

The durable backing-cache node trace completed successfully in commit `c1373d6d71be8bf140335daa7829101634216bd6`, but its raw output was too large for reliable GitHub connector retrieval:

- `report.json` ~51 MB
- `report.txt` ~2.2 MB

A first compact pass still retained 1,113 neighbourhood functions and remained oversized. No new technical conclusion should be inferred from that output-size issue.

To avoid rerunning the static analysis, the branch now contains an essentials-only postprocessor:

- `tools/v0.10.5/extract-lua-backing-cache-essentials.py`
- `tools/v0.10.5/extract-lua-backing-cache-essentials-and-push.ps1`

It reads the existing capture only and emits the six decisive lifecycle functions, cache insert/lookup/creator/helper sequences, and node-field accesses. Use this compact artifact for the next interpretation step rather than repeating the 51 MB trace.

---

# Addendum 2026-09-20 22:0x - durable backing-cache node fields confirmed

Evidence:

- commit `9628f581140750d84b5576773e320ba22a5626ba`
- `archive/field-logs/source-scans/lua-backing-cache-essentials-20260920-190001/`
- existing `lua-client-backing-transfer-20260920-103728` trace for `0x5A6270`

## Cache structure confirmed at instruction level

`LuaContext+0x178` is a sentinel-headed doubly-linked list.

Detach path `0x46538B..0x4653FC`:

```text
rbx = [LuaLevelClient+0x68]   ; durable backing node
0x463C60(rbx)                 ; prepare/finalize backing storage
head = LuaContext+0x178
insert rbx before head        ; [node]=next / [node+8]=prev style links
```

Lookup path `0x465814..`:

```text
resource_key = [[resource+0x30]+0x18]
for node in LuaContext+0x178 list:
    if [node+0x18] == resource_key:
        unlink node
        pass node as R9 to 0x5A6DD0
```

Thus the cache is definitely multi-entry and resource keyed.

## Backing node fields now directly evidenced

From `0x463C60`:

- `+0x00/+0x08` = intrusive doubly-linked-list links
- `+0x10` = 32-bit backing size/count used to decide storage mode
- `+0x18` = resource identity key (confirmed by cache lookup)
- `+0x20` = backing allocator/owner passed as RCX to `0xD1F7F0`
- `+0x28` = optional allocated backing block pointer

`0x463C60` behavior:

- reads size/count from `node+0x10`;
- if value is small (<= `0x410`), leaves `node+0x28 = 0`;
- for larger values, allocates via the owner at `node+0x20` and stores the result at `node+0x28`.

This strongly indicates a small/large backing-storage representation rather than a mere reference-count node.

## Normal/soft payload relocation path

`0x5A6270` handles three length-prefixed client blobs:

- `LuaLevelClient+0x80`
- `LuaLevelClient+0x70` (normal pickle)
- `LuaLevelClient+0x78` (soft pickle)

For each non-null pointer it reads `u32 size` from the first four bytes and copies the payload body into aligned scratch storage. It clears the original client pointer, calls `0x463C60(client+0x68)`, then rebuilds:

- `+0x80` via `0x5A5230`
- `+0x70` via `0x5A6430(..., backing=node)`
- `+0x78` via `0x5A6430(..., backing=node)`

Therefore `0x5A6430` is the critical missing function for locating the durable normal/soft bytes inside or through the backing node.

## Next exact target

Do **not** rerun broad cache or LuaClient scans. Disassemble only:

- `0x464410` — backing-node creator/lookup used when no cached node matches
- `0x5A6430` — normal/soft blob placement using the backing node
- `0x5A5230` — sibling `+0x80` blob placement for comparison
- immediate small callees only

Goal: recover exact backing-node allocation size/layout and the formula mapping each normal/soft serialized payload into durable node storage. Once known, build a focused read-only runtime enumerator over `LuaContext+0x178` rather than any more WAD-by-WAD probes.

---

# Addendum 2026-09-20 22:06 - backing-payload tracer boundary-gap fix

Failed evidence commit: `f32134bba2ddcfdb3d16d7803f4139e174885ab2`  
Failed archive: `archive/field-logs/source-scans/lua-backing-payload-layout-20260920-190632/`

The targeted backing-payload trace failed before producing a report because the PE runtime-function/unwind table does **not** contain a function entry covering direct-call target `0x464410`:

```text
RuntimeError: No runtime function for 0x464410
```

This is a metadata/function-boundary gap, not evidence that the target is invalid. Existing code at `0x465602` directly calls `0x464410`, so it remains a valid backing-node creator/lookup anchor.

Fix commit: `13b5a6cec4bd3b09a8a17bd6c8ce3a9255ec774c`.

The tracer now uses a version-locked raw contiguous fallback **only** for this metadata gap:

```text
0x464410 .. 0x464A50
```

The other targets (`0x5A6430`, `0x5A5230`) still require normal PE runtime-function metadata. Do not broaden the fallback unless a new capture proves another genuine boundary gap.

---

# Addendum 2026-09-20 22:13 - backing payload trace passed; second boundary gap found

Evidence commit: `77198d594ef3f13a6dc9370cbae692814734d503`  
Evidence: `archive/field-logs/source-scans/lua-backing-payload-layout-20260920-191310/`

The targeted payload-layout trace passed after the `0x464410` raw-boundary fix.

## Backing-node creation/cache population

The raw `0x464410..0x464A50` region contains multiple small logical functions, including:

- `0x464410`: find/remove cached backing node by explicit key `[node+0x18] == RDX`;
- `0x464460`: same lookup using `[[resource+0x30]+0x18]`;
- `0x464800`: allocate and initialize a new **0x30-byte durable backing node**.

New-node initialization at `0x464800`:

```text
alloc 0x30 bytes
node+0x00 = 0
node+0x08 = 0
node+0x10 = -1 initially, then assigned backing size/count
node+0x18 = resource key
node+0x20 = allocator/owner allocated from the resource allocator
node+0x28 = optional large backing allocation via 0x5AB340
insert node into LuaContext+0x178 list
```

This confirms the backing-node size is **0x30 bytes** and the previously inferred fields are part of one compact node object.

## Sibling payload format (+0x80) solved

`0x5A5230` rebuilds `LuaLevelClient+0x80` exactly as:

```text
size = R8D
src  = RDX
backing = [client+0x68]
allocator = [backing+0x28]
blob = allocator_alloc(allocator, size + 4)
blob[0:4] = size
blob[4:4+size] = payload
client+0x80 = blob
```

Thus the transient client blob is a conventional **u32 length prefix + payload bytes**, allocated through the durable backing node's `+0x28` allocator/storage object.

## Second unwind/function-boundary gap

The index/runtime-function metadata reports `0x5A6430..0x5A6453`, but the body begins with:

```asm
0x5A6430 test r8,r8
0x5A6433 je 0x5A649F
...
```

So the logical function necessarily continues beyond the indexed end. This is the same kind of unwind-boundary truncation previously seen at `0x464410`.

The current capture therefore does **not yet include the complete normal/soft placement algorithm**. Do not interpret the short `0x5A6430..0x5A6453` fragment as the full function.

Next step: raw-decode a version-locked contiguous range around `0x5A6430` through at least the post-`0x5A649F` return path, then recover the exact mapping used for `client+0x70/+0x78` into the 0x30-byte durable backing node/storage object. No broad scan required.

---

# Addendum 2026-09-20 22:18 - normal/soft backing payload layout SOLVED

Evidence commit: `e75ef2c1fa231fff49e612ce95a26154f4a96c9a`  
Evidence: `archive/field-logs/source-scans/lua-backing-payload-layout-20260920-191808/`

The raw-boundary override for `0x5A6430` worked and exposed the complete logical function through its return at `0x5A649F`.

## `0x5A6430` exact behavior

Inputs at the two known calls from `0x5A6270`:

- RCX = destination client field address (`&client+0x70` or `&client+0x78`)
- EDX = payload size
- R8 = source payload pointer
- R9 = durable backing node (`client+0x68`)

Behavior:

```text
if src == NULL:
    return

size = EDX
allocator_or_store = [backingNode+0x28]
blob = 0xD21A90(allocator_or_store, size + 4)
blob[0:4] = size
memcpy(blob+4, src, size)
*destination_client_field = blob
return
```

Instruction evidence:

```asm
0x5A6458 lea rdx,[rsi+4]
0x5A6465 mov rcx,[r9+0x28]
0x5A6469 call 0xD21A90
0x5A6475 mov [rbx],esi
0x5A647D memcpy(blob+4,src,size)
0x5A6491 mov [r14],rbx
0x5A649F ret
```

Therefore **normal and soft transient blobs have exactly the same conventional representation as the solved +0x80 sibling blob:**

```text
[u32 payload_size][payload bytes]
```

and all three are allocated from the storage/allocator reachable via **`backingNode+0x28`**.

## Relevant helper immediately after it

`0x5A64B0..0x5A64FC` is a separate logical helper. It copies an existing length-prefixed blob into aligned scratch storage and clears the original pointer. This matches the inverse/materialisation flow already seen in `0x5A6270`.

## Durable cache state now solved far enough for runtime enumeration

Backing node:

```text
+0x00 next
+0x08 prev
+0x10 backing size/count
+0x18 resource identity key
+0x20 allocator/owner
+0x28 storage/allocator used for all three length-prefixed blobs
sizeof(node) = 0x30
```

Cache:

```text
LuaContext + 0x178 = sentinel-headed intrusive list of unloaded-resource backing nodes
node+0x18 == [[resource+0x30]+0x18]
```

**Closed question:** do not trace `0x5A6430`, `0x5A5230`, or the normal/soft transient blob format again.

## Next exact target

Resolve the live **LuaContext pointer** at the native cache-lookup/insertion call sites, then build one external read-only `ReadProcessMemory` capture that:

1. locates LuaContext;
2. walks `LuaContext+0x178` safely as a sentinel list;
3. records every cached node's resource key and `+0x10/+0x20/+0x28` fields;
4. reads no save files and performs no process writes;
5. does not yet mutate or force-load any WAD.

Once cache enumeration is proven, correlate resource keys to Raven-bearing resources and decode the backing payload bytes using the already-solved normal/soft materialisation path.

---

# Addendum 2026-09-20 22:20 - LuaContext method calling convention confirmed

Existing constructor/lifecycle evidence was re-read after solving the backing payload format.

`0x4654A0` is confirmed to receive the **LuaContext object directly in RCX**:

```asm
0x4654A0 push rsi
...
0x4654C2 mov rsi,rcx
```

The cache lookup path later preserves and reuses that same object:

```asm
0x4655FF mov rcx,rsi
0x465602 call 0x464410
```

and the direct resource-key walk in the same method uses:

```asm
0x46581C lea rdx,[rcx+0x178]
```

Therefore there is no intermediate wrapper between the method receiver and the cache head: **live LuaContext + 0x178 is the unloaded-resource backing-cache sentinel**.

A static locator has been added to identify the vtable/RTTI slot containing `0x4654A0`, then trace vtable construction and direct callers to a stable singleton/global owner:

- `tools/v0.10.5/trace-lua-context-vtable-singleton.py`
- `tools/v0.10.5/trace-lua-context-vtable-singleton-and-push.ps1`

Once a stable live LuaContext address source is resolved, the next step is an external read-only `ReadProcessMemory` cache enumerator; do not fall back to heap guessing unless the singleton/vtable route fails.

---

# Addendum 2026-09-20 22:23 - LuaContext vtable resolved; singleton route exhausted

Evidence commit: `0b8d0544106913cddc18638e8ce9139d00d44bc9`  
Evidence: `archive/field-logs/source-scans/lua-context-vtable-singleton-20260920-192225/`

The LuaContext class identity is now statically resolved.

## LuaContext vtable

The only non-executable qword pointer to `0x4654A0` is:

```text
0xDF2FB0 -> 0x4654A0
```

RTTI classification identifies the enclosing vtable as:

```text
vtable = 0xDF2F50
RTTI    = .?AVLuaContext@@
slot    = 12  (0xDF2FB0 - 0xDF2F50 = 0x60)
```

Thus a live LuaContext instance can be identified by:

```text
*(u64*)object == module_base + 0xDF2F50
```

## Constructor

`0x4658D0..0x4659B6` is the LuaContext constructor. It installs the LuaContext vtable and explicitly initializes the unloaded-resource cache:

```asm
0x46597B lea rax,[LuaContext_vtable]
0x465982 mov [rbx],rax
0x465985 lea rax,[rbx+0x178]
0x46598C mov [rax],rax
0x46598F mov [rax+8],rax
0x465993 mov word [rbx+0x198],0
0x46599A mov qword [rbx+0x188],0
0x4659A1 mov qword [rbx+0x190],0
```

This independently confirms `LuaContext+0x178` is the sentinel-headed cache list.

## Stable singleton/global owner not found

The static locator found vtable xrefs and constructors, but **no direct caller/global ownership chain** from the indexed call graph (`callers=0`). No reliable RIP-relative singleton pointer was established.

Therefore the preferred singleton route is exhausted for this build. The next runtime locator may now use a strict vtable scan, but it must validate candidates structurally rather than guessing arbitrary heap objects.

## Runtime locator acceptance criteria

A candidate LuaContext is valid only if all are true:

1. `[candidate] == module_base + 0xDF2F50`;
2. `candidate+0x178` is a structurally valid intrusive-list sentinel;
3. sentinel next/prev are readable and reciprocally linked;
4. every walked cache node is readable as 0x30 bytes;
5. each node has reciprocal `next/prev` links and the walk terminates back at the sentinel within a hard node cap;
6. no process writes/debugger/save access are used.

Next: external read-only `ReadProcessMemory` capture that scans committed readable private memory for the exact LuaContext vtable pointer, validates the sentinel, and enumerates cached nodes `(+0x10,+0x18,+0x20,+0x28)`.

---

# Addendum 2026-09-20 22:32 - unloaded Lua backing cache enumerated; +0x18 identity interpretation corrected

Evidence commit: `971320d84330afece7888998b8a8a87b21501af0`  
Evidence: `archive/field-logs/runtime-captures/lua-context-backing-cache-readonly-20260920-193202/`

The first external read-only LuaContext cache capture succeeded using only `VirtualQueryEx` and `ReadProcessMemory`.

## Capture result

```text
result=LUA_CONTEXT_BACKING_CACHE_ENUMERATED
raw_vtable_hits=208
valid_luacontexts=205
nonempty_luacontexts=6
process_memory_written=false
save_opened=false
progression_written=false
```

The six non-empty contexts contained:

```text
context 24  nodes=2
context 114 nodes=1
context 143 nodes=7
context 175 nodes=2
context 181 nodes=13
context 184 nodes=25
```

So the vtable/sentinel discovery and reciprocal list walk are proven in the running game.

## Important correction: node+0x18 is NOT a unique WAD/resource identity

The earlier static lookup showed `[node+0x18]` compared to `[[resource+0x30]+0x18]`, but runtime evidence proves this field is not unique per cached WAD/resource instance.

Examples:

- `0x9184111ADD9F4646` repeats across many distinct nodes, always with backing size `1677721 (0x199999)`;
- `0x8022826DEA3EE5DD` repeats across many distinct nodes with backing size `1258291 (0x133333)`;
- `0xBE4A1AFF9EA71812` repeats across 10 nodes with backing size `1468006 (0x166666)`;
- `0xBA56DDC10047567C` repeats in multiple contexts/nodes with backing size `524288 (0x80000)`.

Therefore `node+0x18` is better described as a **backing/profile/resource-class lookup key**, not a unique WAD identity. Do not use it to map cache nodes directly to Raven WAD filenames.

## Backing allocator layout recovered from captured 0x40-byte previews

Across all non-empty nodes, the object at `node+0x28` / storage pointer has a consistent layout:

```text
storage+0x10 = usable backing arena bytes
storage+0x18 = owner pointer
storage+0x28 = backing arena start pointer
storage+0x30 = 0x200000
storage+0x38 = 0xFFFFFFFFFFFFFFFF
```

And:

```text
storage+0x10 == node.backing_size - 0x410
```

Examples:

```text
0x80000  -> usable 0x7FBF0
0x100000 -> usable 0xFFBF0
0x133333 -> usable 0x132F23
0x166666 -> usable 0x166256
0x199999 -> usable 0x199589
```

Thus the capture already gives a validated contiguous memory arena for each cached backing node without needing to understand the profile key.

## Next exact target

Do not attempt WAD-name correlation through `node+0x18`.

Instead, while the same game process/session remains loaded, scan only the backing arenas of the six proven non-empty LuaContexts for:

1. ASCII `ravenKilled` and checkpoint-table markers;
2. the common Raven custom-userdata prefix `01 b0 b2 27 34 25 30 c2 4e`;
3. all 53 solved `serialized_payload_hex` values from `catalogue/odins-ravens-save-identities.json`.

This is a much stronger authority test because a hit directly identifies the persisted Raven GameObject record inside unloaded backing state. Keep the scan read-only and do not dump whole arenas to Git; record only hit offsets/addresses and small previews.

---

# Addendum 2026-09-20 22:xx - arena scan PID mismatch fixed

Failed evidence commit: `fa1fa77768d148f2849014ba46cccb2f30b4f083`  
Failed archive: `archive/field-logs/runtime-captures/lua-backing-arena-raven-signatures-readonly-20260920-195735/`

The Raven backing-arena signature scan failed before touching arena data because the source LuaContext cache capture belonged to an earlier God of War process:

```text
source pid/base = 11576 / 0x7FF753500000
current pid/base = 30764 / 0x7FF753500000
```

The module base happened to be unchanged, but all heap/cache node pointers from the old PID are invalid after a process restart. The scanner correctly rejected them.

This was a runner-workflow issue, not a failure of the LuaContext/backing-cache model.

Fix commit: `029da47a0e20c466321c1671097eda8a114e8548`.

The arena-scan runner is now self-contained:

1. capture fresh LuaContext/vtable/sentinel/cache-node pointers from the **current** running GoW process;
2. write that fresh source capture inside the same evidence directory;
3. immediately scan only those current non-empty backing arenas for Raven/checkpoint signatures;
4. push the combined evidence.

This removes the requirement that the user preserve the PID from a previous command. It remains read-only: `VirtualQueryEx` + `ReadProcessMemory`, no debugger, no process writes, no save/progression writes.

---

# Addendum 2026-09-20 23:xx - backing-arena raw signature scan negative

Evidence commit: `ba863bb2920b28aeb5413cff20969e48b62234a8`  
Evidence: `archive/field-logs/runtime-captures/lua-backing-arena-raven-signatures-readonly-20260920-200907/`

The self-refreshing read-only arena scan completed successfully against the current GoW process.

## Result

```text
contexts_scanned=6
arena_bytes_scanned=69,573,428
matched_raven_hits=0
unique_matched_ravens=0
ravenKilled_hits=0
__subobjs_hits=0
__PickleTable_hits=0
__SoftPickleTable_hits=0
_SUBOBJECT_CHUNKS_hits=0
process_memory_written=false
save_or_progression_written=false
```

This is a real negative result: the validated backing arenas do **not** expose the raw save-carrier Raven payloads or plaintext checkpoint-table names.

## Interpretation

Do not conclude that the Lua backing-cache route is false. The result is consistent with the already-proven checkpoint architecture:

- save-carrier persistence uses the solved 17-byte serialized GameObject identity;
- checkpoint/SoftPickle tables use opaque runtime GameObject tokens;
- the cached Lua backing representation is therefore not expected to contain the same raw carrier identity bytes;
- checkpoint string/table names may be interned/encoded rather than stored as plaintext in backing allocations.

The stronger correction is that **scanning allocator capacity is not sufficient to locate the logical normal/soft blobs**. We must enumerate or reconstruct live allocations made by the allocator object at `backingNode+0x28`.

## Next exact target

Trace the allocator primitives used by the solved payload materialization path:

- `0xD21A90` — allocation called by `0x5A6430` / sibling blob builders;
- `0xD1F7F0` — backing-storage preparation path from `0x463C60`;
- `0xD21DD0` and nearby allocator helpers where relevant;
- `0x5AB340` — large backing allocation during 0x30-byte node creation.

Goal: recover the allocator control structure and live-allocation metadata well enough to enumerate the actual length-prefixed normal/soft blobs in read-only memory. Do not repeat raw arena signature scans unless live allocation extents become known.

---

# Addendum 2026-09-20 23:xx - LuaContext +0x178 backing-cache route CLOSED

Allocator evidence commit: `12f100c3b0906158c4a791c9b8f96b70892ba5a6`  
Allocator trace: `archive/field-logs/source-scans/lua-backing-allocator-primitives-20260920-201720/`

The allocator trace changes the interpretation of the `LuaContext+0x178` list. These entries are **reusable backing allocator/cache blocks**, not durable per-WAD checkpoint state.

## Exact allocator facts

`0xD21A90` is the allocator used by `0x5A6430`. For a requested payload size it:

- rounds the internal chunk size to at least `0x20` and otherwise 16-byte alignment;
- stores the chunk size/flags in the 8 bytes immediately before the returned user pointer;
- returns `chunk_base + 0x10`;
- tracks allocated bytes at allocator `+0x3A8`;
- uses allocator `+0x28` as the **moving wilderness/free-tail pointer** and allocator `+0x10` as remaining wilderness bytes.

`0xD21DD0` is the matching free/coalesce path.

`0xD1F7F0` initializes the allocator. The object layout observed in the runtime capture matches it exactly:

```text
cache_node +0x20 -> owner object (inline immediately after node)
cache_node +0x28 -> allocator object = owner +0x10
allocator +0x18 -> owner object
allocator +0x10 -> full free wilderness size
allocator +0x28 -> initial wilderness start
allocator +0x30 -> threshold/limit field
allocator +0x38 -> -1 initially
allocator +0x3A8 -> allocated-byte counter
```

## Runtime proof that these cached allocators are empty

For every sampled non-empty `LuaContext+0x178` entry from the read-only capture:

```text
allocator +0x00 = 0
allocator +0x08 = 0
allocator +0x10 = full usable size
allocator +0x20 = 0
allocator +0x28 = initial wilderness start
```

Example:

```text
node     = 0x...6C50
owner    = 0x...6C80 = node+0x30
allocator= 0x...6C90 = owner+0x10
free size= 0x7FBF0
wilderness start = allocator+0x3B0
```

No live allocations are present. This exactly explains why scanning ~69.6 MB from the wilderness regions found zero Raven/checkpoint signatures.

## Corrected architectural conclusion

The `LuaContext+0x178` list is a **cache/pool of reusable backing allocator blocks keyed by profile/size**, not a retained serialized-state authority. The repeated `node+0x18` values and size coupling are allocator-profile keys, not WAD identities.

**Close this route.** Do not perform further arena scans, allocator allocation walks, WAD-key correlation, or treat these nodes as historical checkpoint state.

## Return to strongest unresolved authority boundary

The remaining strongest route is the already-solved global custom-userdata restore path:

- restore root `0x7E9550`;
- carrier descriptor `0x7E7660`;
- record dispatch `0x7E7B60`;
- custom-userdata restore callback at class slot `+0xC0`;
- save-carrier Raven identities are already solved for all 53.

Target the point **before** GameObject userdata is converted into opaque runtime tokens, where the restore machinery still has the serialized custom-userdata record. Determine whether the existing Lua hook/thunk infrastructure can observe this callback or whether a minimal native read-only/instrumentation bridge is required. Avoid returning to save-ring timestamp/slot inference.

---

# Addendum 2026-09-20 23:xx - SerializeHook not a restore interceptor; inspect core.thunk next

Archived persistence-hook evidence was rechecked after closing the Lua backing-cache route.

`engine.SerializeHook` is **not** an interception API for restore. The native handler at `0x4A5D50` directly intersects the proven GameObject token packer `0x60B9C0`; it participates in serialization/token packing rather than exposing the pre-token custom-userdata restore record.

Therefore do not try to solve Raven authority by calling or wrapping `SerializeHook`.

The extracted game Lua source does use `core.thunk` + `thunk.Install(name, fn)` as a real hook-dispatch mechanism (for example locomotion hooks), so the next smallest question is whether that registry has any persistence/restore/pickle-facing hook names that can observe the global custom-userdata restore path without native patching.

New inspection tools:

- `tools/v0.10.5/inspect-thunk-persistence-hooks.py`
- `tools/v0.10.5/inspect-thunk-persistence-hooks-and-push.ps1`

This scan is local-source-only and should be interpreted before considering a native detour/instrumentation bridge.


---

# Addendum 2026-09-20 23:24 - core.thunk persistence route CLOSED; Astra High native pass prepared

Evidence commit from the user-run scan: `238bce84e2ff2f09c3f91234a48886376eeb191a`  
Evidence: `archive/field-logs/source-scans/thunk-persistence-hooks-20260920-202255/`

The extracted Lua-source inspection completed successfully:

```text
lua_files_scanned=500
thunk_install_count=75
unique_names=55
semantic_thunk_install_names=0
```

## Conclusion

`core.thunk` is a genuine shipped hook multiplexer, but no installed thunk names provide a persistence / restore / pickle-facing interception surface. Together with the already-closed `engine.SerializeHook` route, this removes the remaining ordinary Lua-hook option for observing the authoritative pre-token Raven restore stream.

Do **not** repeat searches for a conventional `thunk.Install("OnRestoreCheckpoint", ...)` solution unless later native evidence exposes a previously hidden hook name.

## Current strongest boundary

The unresolved bridge is now specifically the **indirect native dataflow** between the active checkpoint/save loader and the solved custom-userdata restore machinery:

Checkpoint/load side:
- `0x66CB30`
- `0x66ABD0`
- `0x6687F0`
- `0x669300`
- `0x669B00`
- `0x66B650`
- `0x66C080`

Restore side:
- `0x5AEC9E`
- `0x5B2280`
- `0x7E9550`
- `0x7E7660`
- `0x7E7B60`
- `0x7E9190`

Existing direct-call indexing finds no bridge, so the next pass must resolve indirect calls, vtable/interface ownership, callback registration, job/event dispatch, or equivalent data-driven control flow.

The desired interception point is before serialized GameObject identity is converted into opaque runtime tokens, while each custom-userdata record still carries exact persistent identity plus the Raven checkpoint payload.

## Astra High task

Prepared task:

`docs/research/ASTRA-v0105-raven-restore-interceptor-task.md`

Task creation commit:

`5bbf2877b8097252b1325120c20ca7b6284b7345`

Use Astra High for this pass. It is deliberately scoped to recovering the indirect native restore bridge and, if static proof is insufficient, building the smallest self-logging **read-only** observer needed to prove whether all persisted Raven records pass through the restore stream irrespective of WAD residency.

Validation remains the exact Veithurgard fixture:

`false, true, true` and independent RegionSummary `2/3`.

No save/progression writes, no force-load strategy, no nearest-coordinate or aggregate-only inference.


---

# Addendum 2026-09-20 23:xx - Astra High pass hit usage limit after finding native restore bridge

The Astra High Codex pass started from `docs/research/ASTRA-v0105-raven-restore-interceptor-task.md` and pushed its execution plan as commit `52ddebab09ba15de3da18fcca9c8ead1a93cd1ea`.

Codex then hit its account usage limit before it could commit/push the native-analysis evidence. The following findings are therefore recorded as **local Astra findings pending evidence archive/verification**, not yet as final Git-proven facts:

1. The previously separated checkpoint-stage / Lua restore graphs are connected through an indirect virtual call: a checkpoint stage invokes a Lua client vtable slot at **`+0x80`**, and that route reaches the already-known restore root. This explains why earlier direct-call graph searches reported no path.
2. Some earlier function labels around the checkpoint path were semantically wrong: Astra identified `0x669B00` and `0x66B650` as packing/save-side state rather than the restore owner previously implied by broad labels.
3. WAD state appears to live in **separate checkpoint records**. The engine first copies/stages those records, then restores Lua state when the corresponding WAD/Lua context exists. This means the player/global Lua restore call alone does not prove all Raven records are available globally.
4. The interrupted next step was tracing the **stored checkpoint-record bytes themselves** as a possible read-only authority source that may avoid debugger/code-patching entirely.

The final commands Astra was executing before the limit were focused on:

- exact GameObject CodeSideLuaClass descriptor/callback semantics;
- class-key / restore `+0xC0` evidence from archived class-descriptor scans;
- existing active Raven subobject decoder logic;
- narrow disassembly around `0x66AC90:0x66ACBF` and `0x5A6DD0:0x5A6E00`.

## Resume boundary

Do **not** restart the broad native bridge search. Resume by archiving/proving the local Astra finding that checkpoint-stage virtual dispatch `+0x80` reaches the known restore root, then continue from the stored WAD checkpoint-record representation.

Priority questions:

1. What object owns the `+0x80` virtual method, and what exact arguments/state does the checkpoint stage pass into it?
2. Where are the separate WAD checkpoint records stored after the initial copy/staging step?
3. Does that stored representation preserve an exact persistent GameObject/custom-userdata identity before WAD residency is required?
4. Can the already-solved Raven carrier/GameObject decoder read those staged records read-only and recover `ravenKilled` for all 53 catalogue identities?
5. Only if the stored-record route fails should a live observer/debugger interception be reconsidered.

The Veithurgard acceptance fixture remains exact `false,true,true` with RegionSummary `2/3` as an independent cross-check.


---

# Addendum 2026-09-20 - interrupted Astra scratch archived; staged-record proof runner added

Archived Astra scratch commit: `056d24471e33a4b0e69da9e397ea24619da4fb3a`

The previously-local Astra files are now preserved under:

`archive/field-logs/local-handoffs/astra-raven-restore-interrupted-20260920/`

Important recovered static evidence from that scratch:

- `0x464EF0` dispatches through the same LuaClient object at vtable slot `+0x80` at exact sites `0x465143` and `0x4651E2` after preparing a byte buffer and positive length.
- Known Lua restore implementations `0x5AEC60` and `0x5B2280` both call the already-solved restore root `0x7E9550` at `0x5AECAD` and `0x5B22C3` respectively.
- The checkpoint/WAD side uses separate staged records. The interrupted pass had started following candidate storage around the checkpoint record arrays and payload globals instead of treating the loaded player Lua context as global authority.
- `0x669B00` contains substantial packing/copy construction and should not be treated as the restore owner solely from its earlier broad label.

New static tracer:

- `tools/v0.10.5/trace-raven-staged-restore-records.py` added in commit `17d0acb0e5f0c4958b93b482fd2bb7604fa6c111`.
- `tools/v0.10.5/trace-raven-staged-restore-records-and-push.ps1` added in commit `c7ccff61ea01d14937ff2203e78658a45afff7a3`.

The tracer is intentionally bounded and static/read-only. It will:

1. assert the two `+0x80` dispatch instruction bytes;
2. resolve data-pointer-backed vtable candidates whose `+0x80` slot is one of the known restore implementations;
3. prove the direct calls from the level/Lua implementations to `0x7E9550`;
4. enumerate all native references and instruction windows for the candidate staged checkpoint/WAD globals:
   - `0x22C67D0`
   - `0x22C7170`
   - `0x22C7194`
   - `0x22C696C`
   - `0x22C6940`
   - `0x22C6938`;
5. rank functions that touch multiple staging globals so the next read-only runtime capture can target one exact structure instead of scanning memory.

## Exact next action

Run the new static tracer and inspect its pushed report. If it resolves one coherent staged-record owner/layout, build a minimal ReadProcessMemory observer for only that structure and feed those exact staged bytes into the already-solved custom-userdata/Raven decoder. Do not return to raw arena scanning or save-ring timestamp inference.


---

# Addendum 2026-09-20 - staged WAD layout narrowed; targeted read-only Raven observer added

Static evidence commit: `a3a98b8819cf43fc0f9dba2af5da4499dc7f1b00`  
Evidence: `archive/field-logs/source-scans/raven-staged-restore-records-20260920-205034/`

## Proven bridge

The static trace reports `restore_bridge_status=PASS`.

- `0x465143` and `0x4651E2` are exact `call [vtable+0x80]` restore dispatches.
- Base LuaClient vtable candidate `0xE03630` has `+0x80 = 0x5A6C10`.
- LuaClient vtable `0xE04018` has `+0x80 = 0x5B2280`; this vtable is referenced by the known LuaContext/client constructor `0x4654A0`.
- `0x5AECAD -> 0x7E9550` and `0x5B22C3 -> 0x7E9550` are exact direct calls to the solved restore root.

This converts the interrupted Astra bridge finding into archived static proof.

## Staged WAD record layout

The strongest staging owner is `0x668683..0x66878B`, which touches all five relevant fields in one ingest/copy path.

Recovered runtime layout candidate, now narrow enough for direct observation:

- payload pool size: module `+0x22C6938` (u32)
- payload pool base: module `+0x22C6940` (pointer)
- record count: module `+0x22C696C` (u32)
- inline record base: module `+0x22C7170`
- record stride: `0xA8`
- per-record lookup key: `+0x24`
- per-record payload pointer fields: `+0x48`, `+0x50`
- per-record payload byte size: `+0x58`
- per-record name/string storage begins at `+0x84` and fits the remaining `0x24` bytes of the record.

At `0x66871D..0x668758`, the ingest path computes the current payload pointer from the global pool base + size, advances the global payload size, then writes the payload pointer into record `+0x48/+0x50` and the byte count into `+0x58`. This is the smallest current candidate for exact staged checkpoint bytes before WAD-specific Lua restore.

## Targeted runtime observer

Added:

- `tools/v0.10.5/capture-staged-wad-raven-state-readonly.py` in commit `018c6fb333477824bed05f6688ed3efdc094d844`
- `tools/v0.10.5/capture-staged-wad-raven-state-readonly-and-push.ps1` in commit `0fed2b4c7c55b3d7246afe27ba237af41b6dc518`

The observer uses only `PROCESS_VM_READ|PROCESS_QUERY_INFORMATION`. It reads exactly the staged record table and payload extents referenced by it, validates payload pointers against the proven pool extent, and then reuses the solved carrier/GameObject decoder. It records:

- staged record names/keys/sizes;
- exact serialized Raven identity hits across the 53-entry catalogue;
- decoded custom-userdata carriers;
- exact `ravenKilled=true/false` states where present;
- conflicts fail closed.

No arbitrary memory scan, debugger, process write, save access/write, or progression write is used.

## Next acceptance test

Run the staged WAD observer against the loaded almost-complete save. Success means the staged record set exposes exact Raven identities and `ravenKilled` states for unloaded/nonresident WADs as well as the current WAD. If successful, this becomes the authority source for map-open reconstruction. If it only exposes resident WAD records, use its exact record names/layout to identify the higher-level retained checkpoint container rather than returning to broad memory scans.


---

# Addendum 2026-09-20 - global staged WAD table confirmed; exact save identities absent

Runtime evidence commit: `47f6b1ebe96781b22db14cb3c16c84d39a4d7093`  
Evidence: `archive/field-logs/runtime-captures/staged-wad-raven-state-readonly-20260920-205702/`

The targeted observer successfully read the proven staged WAD checkpoint table from the loaded almost-complete save:

```text
record_count=425
pool_size=1055621
records_with_payload=422
payload_bytes_read=9678
records_with_ravenKilled_text=0
records_with_exact_raven_identity=0
records_with_decoded_raven_entries=0
```

This is not a wrong-table failure. The records are clearly global checkpoint/WAD state and include named records across the whole game, including Raven-relevant areas such as:

- `Riv200_DangersMain`
- `Xpl425_HuldraMinesLH`
- `Xpl400_HuldraMines`
- `Xpl220_FuneralLH`
- `Xpl225_FuneralLH`
- `Xpl200_Funeral`
- `Xpl250_FuneralInterior`

Many nontrivial records decode as valid custom-userdata carriers with valid `__subobjs` tables. Therefore the table is the higher-level global staged checkpoint container we were looking for.

However, its `__subobjs` custom-userdata keys do **not** carry the 17/21-byte serialized save GameObject identity. Exact Raven save payload matches across all 53 identities were zero, and plaintext `ravenKilled` was also absent. The state is already in the checkpoint/runtime-token representation at this layer.

Do not discard this route. The crucial new fact is that the global container is found and it includes unloaded WADs. The remaining join problem is now narrowly:

`staged WAD __subobjs opaque GameObject token -> exact Raven catalogue identity`

This is smaller than the previous save/restore authority problem.

A known exact bridge fixture is available from prior Raven identity work:

- VikingFuneral Raven catalogue ID: `raven_642d0d164af0a5d4076e77933c549a5d`
- known runtime packed GameObject token: `0x1BB001DD`
- serialized save identity: `01b0b227342530c24ea9652dba0717be98`

New observer added:

- `tools/v0.10.5/capture-staged-wad-subobject-keys-readonly.py` in commit `fc7b5945e5f7309ac8f3402c1af66ea7f1c34d10`
- `tools/v0.10.5/capture-staged-wad-subobject-keys-readonly-and-push.ps1` in commit `d06e95fe7e2b1b5f8f0b41dd730b96c1a4cec730`

The new capture remains bounded to the proven staged table/payload pool. For every valid `__subobjs` carrier it records the exact custom-record class key, opaque payload bytes, optional u32 interpretation, associated state row/fields, and explicitly checks for the known VikingFuneral token `0x1BB001DD`.

## Exact next boundary

If `0x1BB001DD` appears as a staged `__subobjs` key in one of the Funeral records, the global checkpoint representation is directly joinable to the existing runtime GameObject-token work and we can generalise token generation/matching to all 53 Ravens. If it does not appear, use the captured class-key/payload-length patterns to identify the alternate checkpoint token encoding before any broader search.


---

# Addendum 2026-09-21 - staged SubObject capture proves exact GameObject identity survives globally

Runtime evidence commit: `cdef58d2ef46889f1e8653209780969ef5607bc5`  
Evidence: `archive/field-logs/runtime-captures/staged-wad-subobject-keys-readonly-20260920-210810/`

The global staged WAD table does **not** use opaque 4-byte GameObject keys at this layer. Every captured `__subobjs` custom-record key uses a **17-byte GameObject save-reference payload**.

Most important proof is `Xpl200_Funeral`:

```text
01b0b227342530c24ee561807520d55c16
01b0b227342530c24ea0a803505c2eb7ad
```

These are exactly the two known non-Raven GameObject identities from the frozen VikingFuneral fixture. Their state rows contain `mapSummaryComplete=true`.

The known Raven identity from the same frozen fixture:

```text
01b0b227342530c24ea9652dba0717be98
```

is absent from the first staged payload pool. The broader 53-Raven exact-identity scan also found zero Raven identities there.

Therefore:

1. the global staged WAD table preserves the solved persistent GameObject identity format exactly;
2. identity decoding/joining is no longer the blocker;
3. the first staged payload channel contains ordinary WAD checkpoint state, including the two companion Funeral GameObjects;
4. Raven `ravenKilled` persistence must be carried in a **parallel checkpoint/SoftPickle channel** associated with the same global WAD/save machinery, rather than being transformed into an opaque runtime token at this point.

The prior expectation that `0x1BB001DD` should appear directly in this staged carrier was therefore incorrect; zero hits are now explained by the fact that this layer still stores the 17-byte save-reference form.

New static tooling added to locate the parallel stream without broad scanning:

- `tools/v0.10.5/trace-staged-wad-parallel-channels.py` in commit `85b79785fb98ad83fd455f789ef85be113170c8b`
- `tools/v0.10.5/trace-staged-wad-parallel-channels-and-push.ps1` in commit `1295ade78a9a18533a39184002ca808c78a4b79d`

The tracer enumerates all RIP-referenced globals in the narrow staging band `0x22C6900..0x22C7200`, references into the `0xA8` WAD-record structure, and full disassembly for the checkpoint creation/consumption functions around `0x667xxx`, `0x668xxx`, `0x669xxx`, and `0x82Dxxx`.

## Exact next target

Identify the neighbouring pointer/size globals or per-record descriptor used by the parallel SoftPickle/checkpoint stream. Then capture only that stream for `Xpl200_Funeral` and test for the exact Raven payload `01b0...a9652dba0717be98` plus its `ravenKilled` state. Do not return to broad memory scanning or save-ring authority inference.


---

# Addendum 2026-09-21 - second staged WAD payload descriptor proven

Static evidence commit: `32fb41774e3c085a2e9be316c142494662bc2323`  
Evidence: `archive/field-logs/source-scans/staged-wad-parallel-channels-20260920-212109/`

The narrow staging-band trace resolves the previously missing parallel payload layout inside each `0xA8` WAD record.

Two independent variable payload descriptors exist:

- **channel A / SoftPickle candidate**: pointer fields `+0x30/+0x38`, byte size `+0x40`
- **channel B / ordinary WAD checkpoint payload**: pointer fields `+0x48/+0x50`, byte size `+0x58`

Both are backed by the same global payload pool at module `+0x22C6940` with running size at `+0x22C6938`.

Native proof is in `0x82CF00`:

- it reads the full `0xA8` staged record;
- takes `dword [record+0x40]` as a variable payload length;
- computes `pool_base + current_size`;
- stores that pointer into `record+0x30` and `record+0x38`;
- reads exactly that payload length into the shared pool and advances the pool size.

The earlier observer only inspected `+0x48/+0x50/+0x58`, explaining why it saw ordinary checkpoint state and the two companion Funeral GameObjects but not the Raven record.

Additional relevant structure:

- `record+0x20` contains flags/state bits used by `0x82D760` and related code;
- `record+0x24` is the stable per-WAD key/ID;
- `record+0x84` is the WAD record name/string storage;
- `0x82D660` restores/frees channel-B payload using `record+0x48/+0x58`;
- `0x82D760` separately restores/frees channel-A payload via `record+0x30/+0x40`.

New bounded runtime tooling:

- `tools/v0.10.5/capture-staged-wad-dual-payload-raven-state-readonly.py` in commit `13496895ab7542078f41822195787b583efa6277`
- `tools/v0.10.5/capture-staged-wad-dual-payload-raven-state-readonly-and-push.ps1` in commit `cfadb742607d2bbf4f4553d7a63b2a3a3ecaae6c`

It reads both proven descriptors only, validates all pointers against the shared pool extent, exact-matches all 53 serialized Raven GameObject identities, and reuses the solved Raven custom-userdata decoder.

## Exact next acceptance test

Run the dual-channel observer on the almost-complete save. The decisive result is whether channel A contains:

```text
01b0b227342530c24ea9652dba0717be98
```

for the VikingFuneral Raven and ideally decodes its `ravenKilled` field. If channel A yields the Raven entries, this becomes the authoritative global map-open reconstruction source. If the identity appears but graph decode fails, inspect only that carrier framing/state table next; do not broaden the search.


---

# Addendum 2026-09-21 - dual staged payload capture negative; move to exact native consumer trace

Runtime evidence commit: `109fcaeac781a6c80e40dc58ae1bf6e4819606c6`  
Evidence: `archive/field-logs/runtime-captures/staged-wad-dual-payload-raven-state-readonly-20260921-052345/`

The dual-channel runtime observer successfully read both proven variable-payload descriptors for all 425 staged WAD records.

Results:

```text
record_count=425
pool_size=1055845
total_payload_bytes_read=1055845

Channel A (+0x30/+0x38, +0x40 size):
  payload_records=425
  payload_bytes=1046167
  exact Raven identity count=0
  decoded Raven entries=0

Channel B (+0x48/+0x50, +0x58 size):
  payload_records=422
  payload_bytes=9678
  exact Raven identity count=0
  decoded Raven entries=0

known VikingFuneral Raven identity hits=0
conflicts=0
```

This is a genuine negative for both staged variable payload channels on the loaded almost-complete save. Channel A is very large and accounts for essentially the entire remainder of the shared pool, but it is not a direct custom-userdata carrier stream and contains none of the 53 serialized Raven GameObject identities. Channel B remains the small ordinary WAD checkpoint custom-userdata stream already characterised earlier.

Concrete Funeral example:

- `Xpl200_Funeral` record index 220 / key `0xEE`
- Channel A size `22505`, SHA-256 `87d0864cae15f95573cf6d329065b0775fb12461a5dd912f66bd0dacea944734`
- Channel B size `155`, SHA-256 `2d1ecac2a96a3e30eb10edfce7e5860291ef55ba3099c1db7b45a0e8c6fa39a4`
- neither channel contains `01b0b227342530c24ea9652dba0717be98`.

Do not repeat broader pool scans. The next boundary is now the **native consumer/transform of Channel A and the remaining non-payload fields of the 0xA8 record**, plus any separate checkpoint stream outside this record table.

Important static facts retained:

- Channel A descriptor = record `+0x30/+0x38/+0x40`.
- Channel B descriptor = record `+0x48/+0x50/+0x58`.
- record `+0x20` is flags/state bits.
- record `+0x24` is stable WAD key/ID.
- record `+0x84` is name/string storage.
- `0x82D760` explicitly frees/restores Channel A through `0x667230` using descriptor `record+0x30`.
- `0x82D660` separately restores/frees Channel B.
- the custom-userdata restore bridge remains proven: LuaClient vtable `+0x80 -> 0x5B2280 -> 0x7E9550`.

## New Codex/Astra boundary

Use a fresh high-reasoning native pass to trace exactly where Channel A is consumed/transformed and whether another record field or external per-WAD/global structure carries the Lua custom-userdata stream. Start from concrete field accesses and object ownership, not broad xrefs.

Primary functions to analyse first:

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

Required end result is one of:

1. identify the exact transform/destination of Channel A and a later transient buffer that contains the Raven carrier; or
2. prove Channel A is unrelated to Lua checkpoint state and identify the separate global checkpoint structure that feeds `0x465143/0x4651E2 -> LuaClient+0x80 -> 0x5B2280 -> 0x7E9550`.

Do not redo GameObject codec, carrier framing, raw allocator scans, save-ring timestamp inference, RegionSummary inference, or ordinary Lua thunk searches.


## Fresh Astra/Codex task prepared

A new tightly scoped high-reasoning task was added in commit `805c19048fe8881a3ac411edf1627986066a3b96`:

`docs/research/ASTRA-v0105-raven-missing-checkpoint-stream-task.md`

Use this task instead of the older broad restore-interceptor task. It incorporates the dual-channel negative and directs analysis toward the exact Channel-A consumer / LuaClient restore-buffer provenance boundary.


---

# Addendum 2026-09-21 - interrupted Astra pass reports Channel-A bitstream restore path

The fresh Astra High pass against `docs/research/ASTRA-v0105-raven-missing-checkpoint-stream-task.md` hit its usage limit before any of its new edits were committed or pushed. The remote branch therefore still ended at `76c46b5b9c798cc872930694e99b131941a3a009` when this note was added.

The following are **reported local Astra findings pending preservation and independent verification**, not yet Git-proven facts:

1. Channel A is interpreted as a **packed bitstream**. Therefore the earlier raw-byte exact-identity search cannot rule out Raven state in Channel A.
2. Astra traced the native path far enough to conclude that Channel A is consumed by a bit reader and produces a **per-WAD Lua restore buffer**, which then feeds the already-proven Lua restore dispatcher.
3. This explains why Channel A can be the authority source even though none of the 17-byte Raven identities appear byte-aligned in its raw bytes.
4. Astra began implementing a bounded bitstream reader/decoder and intended to keep the raw Channel-A bytes for offline replay against known alive/dead Raven fixtures.
5. The game was closed at the end of the pass; Astra expected one final live validation command after finishing/reviewing the decoder.
6. The interrupted local work reportedly modified five files, including `docs/superpowers/plans/2026-09-21-raven-missing-checkpoint-stream.md`, but those changes were not pushed before the quota limit.

## Immediate recovery boundary

Before pulling/resetting/restarting Codex, preserve or commit the existing local working-tree edits from the interrupted Astra pass. Then review the exact native bit-reader semantics and the new decoder before treating the Channel-A claim as proven.

If the local decoder is sound, the next acceptance target remains exact Raven state recovery from the existing staged Channel-A bytes, followed by one live read-only validation against the almost-complete save and the Veithurgard `false,true,true` fixture.


---

# Addendum 2026-09-21 - interrupted Astra bitstream work preserved and reviewed

Preserved/rebased/pushed Astra work commit: `45c820a`  
Original local preservation commit before rebase: `898fce0`

Files now preserved on the Raven branch:

- `docs/superpowers/plans/2026-09-21-raven-missing-checkpoint-stream.md`
- `tools/v0.10.5/staged_wad_bitstream.py`
- `tools/v0.10.5/capture-staged-wad-bitstream-raven-state-readonly.py`
- `tools/v0.10.5/capture-staged-wad-bitstream-raven-state-readonly-and-push.ps1`
- `tools/v0.10.5/test_staged_wad_bitstream.py`
- `tools/v0.10.5/test_staged_wad_bitstream_capture.py`
- `tools/v0.10.5/trace-staged-wad-bitstream-boundary.py`
- static evidence under `archive/field-logs/source-scans/staged-wad-bitstream-boundary-20260921/`

## Static path now pinned by Astra tooling

The new static tracer explicitly archives these native windows:

- Channel-A writer: `0x82B250..0x82B42D`
- Lua bit writer: `0x23F9C0..0x23FA94`
- Channel-A read/cursor reset: `0x6740E1..0x674133`
- bit-reader init/slot lookup: `0x82C4E0..0x82C6A0`
- Lua bit reader: `0x23FE12..0x23FE97`
- checkpoint LuaClient restore call: `0x24001D..0x240078`
- MSB bit read/write helpers: `0xA20280..0xA20326` / `0xA20220..0xA20280`
- full WAD bit restore: `0x23FAA0..0x240078`
- live client roundtrip: `0x464EF0..0x465225`
- client restore/deferred copy: `0x5B2280..0x5B249F`

This is the first preserved implementation that directly models Channel A as an MSB-first packed bitstream feeding a per-WAD Lua restore buffer and then the known LuaClient restore path.

## Important decoder status

`tools/v0.10.5/staged_wad_bitstream.py` is deliberately fail-closed and labels all output:

```text
classification=CANDIDATE
production_ready=false
enclosing_field_traversal_validated=false
```

The current offline extractor:

- treats the outer Channel-A envelope as little-endian u16 length + packed bytes;
- checks all eight bit alignments;
- reconstructs nested candidate Lua buffers using MSB-first u16 lengths;
- reuses the solved Raven custom-userdata decoder rather than introducing a second codec;
- keeps missing Raven state as unknown;
- rejects conflicting/ambiguous parses and bounded-work cap hits;
- can archive raw Channel-A payloads for deterministic offline replay.

The RPM capture performs two equal bounded reads of the proven staged table and pool and rejects changed snapshots. It still correctly reports `production_ready=false`.

## Remaining authority gates

Do NOT integrate candidate output into the map yet. The following still need proof:

1. prove the exact enclosing Channel-A field traversal/position rather than finding a syntactically valid carrier at some bit alignment;
2. prove active-checkpoint freshness of the staged payload used by the observer;
3. prove state recovery for unloaded/nonresident WADs;
4. validate exact Veithurgard `false,true,true` and at least one second region;
5. independently review the bit ordering/length semantics against the archived native instructions.

A live capture runner already exists:

`tools/v0.10.5/capture-staged-wad-bitstream-raven-state-readonly-and-push.ps1`

It requires God of War running on the advanced save and paused, archives all raw Channel-A bytes plus candidate decode results, commits the runtime evidence, and pushes it. Use only after remaining local scratch/research artifacts from the interrupted Astra pass have been preserved so no evidence is lost.


---

# Addendum 2026-09-21 - Channel-A candidate capture tightened with native Lua-length cross-check

Commit: `f0c6544505600baf1db6b81b713270f21607242d`

Recovered Astra static notes prove that staged record `+0x60` is the cached Channel-A Lua byte count copied from the native WAD slot's `+0x5E10` field. The live candidate observer now reads this field and passes it into `staged_wad_bitstream.extract_channel_a(..., expected_lua_length=...)`.

This means a bit-aligned nested carrier candidate is accepted only when its decoded nested length also equals the engine's own cached Lua length for that WAD record. The observer remains explicitly candidate-only and production authority is still gated on exact enclosing-field traversal, freshness, unloaded-WAD validation, and the Veithurgard fixture.

Recovered static notes additionally establish:

- Channel A is not compressed;
- the Lua payload is written as a 16-bit length followed by 8-bit bytes into an MSB-first bitstream;
- `0x23FAA0` restores the larger WAD bitstream;
- `0x23FE25` reads the Lua length with a 16-bit MSB-first read;
- `0x23FE63` reads each Lua byte with an 8-bit MSB-first read;
- `0x240047` calls `LuaClient+0x80` using `RDX=slot+0x5E14`, `R8D=slot+0x5E10`;
- the per-record Channel-A pool slice is retained for nonresident WADs, so an offline/read-only decoder can in principle recover unloaded Raven state without force-loading WADs.

The next runtime capture should therefore archive every Channel-A slice and apply the engine Lua-length cross-check. Any decoded Raven states remain candidates until exact native prefix traversal is reproduced.


---

# Addendum 2026-09-21 - packed Channel-A live capture and exact native-length framing

Runtime capture commit: `f907d2dfd555253b054274dfe2f565876b2f9c64`  
Evidence: `archive/field-logs/runtime-captures/staged-wad-bitstream-raven-20260921-060345-c2c9bcc1/`

Capture result before decoder refinement:

```text
record_count=425
pool_size=1055640
candidate_state_count=0
unknown_count=53
production_ready=false
```

This zero-state result was caused by the conservative broad zlib marker cap on large WADs, not by failure of the native-length framing. Most non-empty records already produced exactly one Lua carrier candidate when checked against record `+0x60` cached Lua length. Large WADs such as `Xpl200_Funeral` hit `stream_marker_cap` before candidate evaluation.

Decoder refinement commit: `89bb607e44c213556aee2cfb18cafd0ec3454f45`

When `expected_lua_length` is known, `staged_wad_bitstream.extract_channel_a` now follows the proven native restore framing directly:

1. search each of the eight MSB bit phases for the exact 16-bit big-endian Lua byte count from staged record `+0x60`;
2. take exactly that many following 8-bit bytes as the Lua buffer;
3. require the solved custom-userdata carrier to begin at that exact buffer start;
4. require valid zlib at carrier offset `+0x10` and exact header/decompressed-length consistency;
5. reuse the canonical Raven carrier graph decoder.

This removes the unrelated whole-WAD `0x78` marker cap from the native-length path without weakening fail-closed validation.

Offline replay tooling:

- `9a40190f928b71c2e398c49bd27cb3e5d376ebde` adds `tools/v0.10.5/replay-staged-wad-bitstream-capture.py`.
- `3ff3ef4dc50b0089f4124667dc70d55332cc9bcd` adds regression coverage proving native-length framing bypasses unrelated marker-cap noise.

## Concrete Xpl200_Funeral boundary from archived raw bytes

The live capture contains:

- record index: `220`
- WAD: `Xpl200_Funeral`
- Channel-A bytes: `22518` total including outer u16 envelope
- cached Lua length from record `+0x60`: `9841`

Across all eight MSB phases, the value `9841` appears at only two candidate length positions:

- alignment 0, byte 11907 -> candidate buffer start 11909 -> bit offset `95272`; rejected because carrier offset `+0x10` is not a valid zlib stream;
- alignment 3, byte 11407 -> candidate buffer start 11409 -> bit offset `91275`; **valid zlib stream at carrier offset +0x10** and therefore the only surviving native carrier position before canonical graph decoding.

This is the strongest current concrete proof that the staged Channel-A bitstream contains the per-WAD Lua restore carrier at a deterministic bit position. Next step is offline replay of the already captured 425 Channel-A slices with the refined decoder. No new game capture is required for that step.


---

# Addendum 2026-09-21 - exact-length replay test fix

Commit: `0125cdf7a6663cad4d5fe2fb9fe0b4601e2526f0`

The first offline replay attempt stopped in `test_cached_lua_length_is_only_cross_check`. This was a decoder-reporting bug introduced by the new exact native-length framing, not a failure of the captured Channel-A data.

With `expected_lua_length` supplied, the refined decoder searches the eight MSB bit phases for that exact 16-bit big-endian length. If the supplied length is deliberately wrong, there may be no matching positions at all. The decoder previously returned zero candidates with an empty rejection list, while the existing fail-closed regression correctly expected an explicit `cached_lua_length_mismatch` reason.

The decoder now records `cached_lua_length_mismatch` when no native length position matches the staged record's expected Lua length. No capture format, native framing, Raven codec, or runtime evidence changed.


---

# Addendum 2026-09-21 - authoritative Veithurgard packed-state decode achieved

Offline replay evidence commit: `d4557a547a19247b4d15a6bd0c4dba38f0f57fed`

Evidence:
`archive/field-logs/runtime-captures/staged-wad-bitstream-raven-20260921-060345-c2c9bcc1/replay-report.{json,txt}`

The refined native-length Channel-A replay recovered the exact three `Xpl200_Funeral` Raven states from the live advanced-save capture with one unambiguous Lua carrier candidate at bit offset `91275`:

- `raven_642d0d164af0a5d4076e77933c549a5d` -> `ravenKilled=false`
  - native world position approximately `(-64.8509, 12.9874, 787.3069)`
- `raven_e32f7bab42fd7298890f6aa56a734562` -> `ravenKilled=true`
  - native world position approximately `(-127.9608, 15.5776, 690.0758)`
- `raven_c945cb53465b58decfcbd4a221cb5326` -> `ravenKilled=true`
  - native world position approximately `(122.6049, 17.3743, 679.2116)`

This exactly matches the independently established Veithurgard acceptance fixture `false,true,true` and RegionSummary count `2/3`.

This is the first successful recovery of exact per-Raven authoritative checkpoint state for a nonresident WAD from the packed Channel-A stream, using only read-only runtime capture plus offline decode. It closes the core question of whether Channel A actually carries the Lua Raven state.

## Broader coverage finding

The 53-Raven catalogue spans 39 unique WADs. The captured staged WAD table contains exact-name Channel-A records for 30 of those WADs, covering 42 of the 53 Raven catalogue entries. Only the three Veithurgard identities currently join to catalogue IDs, but many other decoded Lua carriers explicitly contain the string `ravenKilled`, including Raven-bearing WADs such as:

- `Riv200_DangersMain`
- `Xpl940_BeachCave`
- `Foot500_Top`
- `Alf355_ChiselDungeon`
- `Peak140_CavernDark`
- `Xpl850_DungeonForest`
- `Xpl300_Stronghold`
- `Hel300_MainBridge`

Therefore the next blocker is not missing Lua state. It is the save-side GameObject identity join for Raven subobjects outside `Xpl200_Funeral`.

Next step: instrument the canonical carrier decoder to report **all registry-matching GameObject subobject keys whose state row contains `ravenKilled`**, including unmatched object hashes/payloads. Compare those live save identities against the 53 catalogue identities and recover the remaining transform/join rule. Do not fall back to coordinates, RegionSummary-only inference, or absence=alive.


---

# Addendum 2026-09-21 - identity-join diagnostic for non-Veithurgard Raven WADs

Commits:

- `e932ab091f01e5cc0d2ec91c67430f1201428014` - canonical carrier decoder now preserves all registry-matching GameObject subobject identities whose state row contains an explicit `ravenKilled` boolean, even when the object hash does not match the current 53-entry catalogue map.
- `b9ea909a7b165a872f7a115b40999a98f35b60e8` - offline replay text report prints unmatched Raven-state identities with exact record payload hex, object hash, state row, and boolean state.
- `a9d23d6f2ba6808376fa60308cc4f5db9a90cda7` - regression coverage proves unmatched Raven-state identities are retained rather than discarded.

The diagnostic fields added to decoded carriers are:

- `raven_state_entries_all`
- `unmatched_raven_state_entries`

Each unmatched entry preserves:

- complete native GameObject record payload hex;
- flags / aux / upper form;
- registry hash;
- object hash;
- exact state row;
- explicit `ravenKilled=true|false`.

This is specifically intended to solve the remaining identity join for the other Raven-bearing WADs. The decoded Lua carriers for many of those WADs already contain `ravenKilled`, so the next offline replay should expose their actual save-side GameObject identities directly.

No new runtime capture is required. Re-run the archived `20260921-060345-c2c9bcc1` capture through the current decoder and compare unmatched payloads against the 53 catalogue identity transform chains.


---

# Addendum 2026-09-21 - Raven state parent-key diagnostic

Commits:

- `4e4c25ba1f0ae45b7661b5bb79143bdb9eeae0e3` - canonical carrier decoder now records the exact `__subobjs` parent key for every target state row containing an explicit `ravenKilled` boolean, before applying any GameObject or registry assumptions.
- `4f4bf3ba86537d19c10dd4fa9ee5ae906ef85c4e` - offline replay text output prints those Raven state parent keys.
- `e23207219f2a66bb9116119f540e7f47b6435a20` - regression coverage for parent-key preservation.

New diagnostic field:

- `raven_state_parent_keys`

For each explicit `ravenKilled` state row it records:

- subobject table row and target state row;
- boolean state;
- key token tag, payload, width, and raw token bytes;
- if key tag 5 references a userdata record: record index, class key, and complete record payload;
- if that payload parses as a native GameObject reference: flags, aux, upper form, registry hash, object hash, and current catalogue match if any.

Reason for this diagnostic: the latest replay found zero `unmatched_raven_state_entries` under the solved Raven registry outside `Xpl200_Funeral`, even though many Raven-bearing WAD carriers contain the `ravenKilled` string. Therefore the other Raven state rows are likely attached to a different key representation/registry rather than merely a different object hash under `0x4EC230253427B2B0`.

Next step is an offline replay of the existing `20260921-060345-c2c9bcc1` capture and direct comparison of `RAVEN_STATE_PARENT` rows across Raven-bearing WADs. No game run is required.
