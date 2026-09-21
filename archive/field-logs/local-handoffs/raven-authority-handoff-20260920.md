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


---

# Addendum 2026-09-21 - WAD-specific registry hash solved; nested-container static solver added

Commits:

- `b5c5278dc48e3b68025f776039bd009924054bc8` - serialized Raven identity builder no longer hard-codes `0x4EC230253427B2B0`; registry hash is now `name_hash(lowercase WAD stem)`.
- `81d1252d496fc6d6f2e6e3f5c1a77fa7f5cf730f` - adds a static nested-container identity solver.
- `3b4d4ae4006eb9d8df8d7a543c577e09e3d2bb77` - adds the push runner for that solver.

## Registry-hash proof

The first 64-bit field of the 17-byte GameObject save reference is WAD-specific and exactly equals the existing native case-folded `0x401` name hash of the WAD stem without `.wad`.

Examples proven against packed Channel-A Raven-state parent keys:

- `xpl200_funeral` -> `0x4EC230253427B2B0`
- `riv200_dangersmain` -> `0x30069EB304D9166F`
- `xpl940_beachcave` -> `0xAA77EDBE6D4D1BA8`
- `foot500_top` -> `0x0BCCD9FC102E3064`
- `alf355_chiseldungeon` -> `0x90911C68B1E5C2C8`
- `peak140_caverndark` -> `0x36ACCE93A6D929FF`
- `xpl850_dungeonforest` -> `0xBAF9C8514445A1D3`
- `xpl300_stronghold` -> `0x72F3920BE9DF209F`
- `hel300_mainbridge` -> `0x86D134ABFB78D5BC`

This disproves the previous assumption that the VikingFuneral registry hash was shared by all Raven save references.

## Object-hash split

For ordinary Raven transform chains, the existing static object-hash algorithm already matches the live packed checkpoint object hashes exactly. Verified examples include Riv200, Foot500, Alf355, Peak140, Hel300, and Xpl200.

Object-hash mismatches are concentrated in Raven objects nested under special intermediate Raven containers such as:

- `goProtoRaven_03` / `goraven_03` in Xpl940;
- `goProtoRavens` / `goravens` in Xpl850;
- `goProtoSpecial_Ravens_03` / `gospecial_ravens_03` in Xpl300.

The final object's `parent_prototype_id` is only the already-known byte-12-decremented group record ID and is therefore not itself the missing extra element.

## Static nested-container solver

`resolve-raven-nested-container-identities-static.py` reads only shipped WAD files, the canonical Raven catalogue, and the archived packed replay. For any catalogue Raven whose current static object hash does not match a live object hash in that WAD, it:

1. locates the final Raven object's parent prototype record;
2. scans that record for references to 16-byte WAD record IDs;
3. tests both raw and byte-12-decremented candidate identity elements;
4. inserts each candidate at every possible position in the existing identity vector;
5. accepts a solution only when the rebuilt native `0x401` identity hash exactly equals an observed live checkpoint object hash from that same WAD.

No process access or save writes are used. The next step is to run this static solver locally against the shipped WADs and inspect whether the nested cases resolve uniquely.


---

# Addendum 2026-09-21 - nested identity insertion model rejected; replacement model added

Runtime-backed static solver evidence commit: `e58b0cecfee2d24160cfaa24631e092b4cff50a2`

Result:

```text
catalogue_rows_with_live_wad=42
base_hash_matches_live=31
unique_solution=0
multiple_solutions=0
no_solution=11
parent_prototype_record_missing=0
```

Interpretation:

- 31 of the 42 Ravens represented in the live packed checkpoint already match the existing static object-hash reconstruction exactly.
- All 11 failures are nested-container cases.
- The first solver tested whether one referenced parent-prototype identity element could simply be inserted anywhere in the existing identity vector. None of the 11 live hashes matched that model.
- Therefore the missing native parent contribution is not a simple additive element under the current sequence.

Commit `4f0f0e347af8824b3bcf5a21500f722ab6f3547c` extends the static solver with the next native model: a parent object's own `object+0x40` identity element may **replace** the simplified transform-record-derived element currently used for that intermediate parent. The solver now tests both insertion and one-for-one replacement, still accepting only exact equality with live packed-checkpoint object hashes.

Next step: rerun the same static solver. If replacement resolves the 11 cases uniquely, fold those parent identity elements into the 53-entry serialized Raven identity generator. If it still fails, inspect the full parent metadata vector rather than guessing additional elements.


---

# Addendum 2026-09-21 - reversible native hash solver for nested Raven parents

Second insert/replace evidence commit: `403c9a3707c025b128ead480164706722727d286`

The second static run remained unchanged:

```text
catalogue_rows_with_live_wad=42
base_hash_matches_live=31
unique_solution=0
multiple_solutions=0
no_solution=11
parent_prototype_record_missing=0
```

Therefore both single-element hypotheses are closed:

1. inserting one parent-derived element anywhere in the simplified identity vector;
2. replacing one existing element with one parent-derived element.

Commit `10b2a20fb39df6a435628aa078bc497cb65fd153` replaces that heuristic search with a reversible-hash solver.

## Reversible-hash method

The native identity hash updates one byte as:

```text
x = ((state + byte) * 0x401) mod 2^64
next = x XOR (x >> 6)
```

Because `0x401` is odd, multiplication is invertible modulo `2^64`, and the right-xorshift is also invertible. The new solver implements an exact byte inverse and self-tests that complete known identity vectors reverse back to state zero.

For each nested Raven row, the solver reverses its known child-record identity element and final Raven prototype identity element from every observed live checkpoint object hash. For siblings under the same intermediate parent, the correct live-hash assignment must yield the same 64-bit state immediately after the parent's native identity contribution.

The solver then:

1. requires one common recovered post-parent state across siblings;
2. verifies the outer transform prefix state is common;
3. scans every 16-byte sliding window of the 784-byte parent prototype record, plus byte-12-adjusted variants and explicit parent IDs;
4. tests exact one-element parent vectors;
5. tests exact two-element parent vectors with a meet-in-the-middle forward/reverse state join;
6. accepts only exact 64-bit equality with the recovered parent state;
7. if exactly one parent vector survives, rebuilds every nested Raven identity and verifies it against its assigned live checkpoint hash.

This converts the remaining 11 nested cases from placement guessing into an exact constraint problem driven by the archived live checkpoint hashes. No game process or save access is required.


---

# Addendum 2026-09-21 - self-prototype parent skip rule solved and pipeline integration started

Reversible-hash evidence commit: `a432ad325f2982ec3d0426acf516149fab47f2c1`.

The reversible solver produced a decisive result in all six unresolved WADs: the recovered native hash state immediately after the intermediate parent was **identical to the hash state immediately before that parent**. Therefore the intermediate parent contributes zero GameObject identity elements.

This exactly explains all 11 live object-hash mismatches.

## Static discriminator

Across the full 53-Raven catalogue, exactly 11 rows satisfy:

```text
adjusted_record_id(transform_chain[1].record_id) == native.parent_prototype_id
```

where `adjusted_record_id` decrements byte index 12 modulo 256.

Those 11 rows are exactly the 11 live-mismatching nested-container Ravens. No other Raven row satisfies the condition, and there are no non-matching long transform chains outside this set.

The affected immediate parent container names are examples such as:

- `goraven_03`
- `goraven_01`
- `goravens`
- `gochallenges`
- `gospecial_ravens_03`

This is a structural rule, not a WAD-name special case.

## Pipeline commits

- `3529d350413dc4071aa85632fc8023741f579193` - serialized Raven identity generator now omits an immediate self-prototype parent when the adjusted parent transform ID equals `native.parent_prototype_id`.
- `915e07cd5b78d0bedfb22c3010164f63d5ff14a0` - canonical Raven carrier decoder can resolve catalogue IDs by the full `(registry_hash, object_hash)` pair when no single global registry is supplied.
- `6166a58a7607837e6e48f4a27d39ffbd68d240fe` - offline staged replay now loads `catalogue/odins-ravens-gameobject-identities.json` and builds a 53-entry pair map.
- `5b5ca8a39fd567d8dca0cb5a56c0ace0ab09fdd5` - live staged observer likewise uses the per-WAD pair map.
- `d5dc72f36d7812c21ea5f5f94fd7e57c636baa64` - regression coverage proves a frozen Raven carrier resolves correctly through a `(registry, object)` identity map with no global-registry assumption.

## Expected next acceptance result

After regenerating `catalogue/odins-ravens-gameobject-identities.json` with the corrected self-prototype skip rule and WAD-derived registry hashes, an offline replay of the existing `20260921-060345-c2c9bcc1` Channel-A capture should resolve all **42 Raven state rows whose Raven-bearing WADs are present in that staged table**, not just the three Xpl200_Funeral Ravens.

No new game capture is required for this acceptance test.


---

# Addendum 2026-09-21 - 42/42 staged Raven states resolved exactly

Identity regeneration commit: `c9eca47e98f46e7fe2737498f82bd68f7f479025`

Offline replay acceptance commit: `aa340337eed96e4c135640ce722a9721f7d9bf68`

The corrected 53-entry serialized GameObject identity catalogue plus per-WAD `(registry_hash, object_hash)` matching successfully resolves every Raven state row present in the archived staged Channel-A snapshot.

Acceptance result:

```text
candidate_state_count=42
unknown_count=11
production_ready=false
```

Detailed consistency checks:

- 42 exact Raven catalogue IDs resolved;
- 27 explicit `ravenKilled=true`;
- 15 explicit `ravenKilled=false`;
- 30 Raven-bearing Lua carriers;
- 42 `RAVEN_STATE_PARENT` rows;
- zero ambiguous records;
- zero conflicting Raven states;
- zero unmatched Raven-state GameObject keys.

Previously broken self-prototype-container cases now resolve exactly, including Xpl940_BeachCave, Xpl970_BeachTower, Xpl425_HuldraMinesLH, Xpl850_DungeonForest, Xpl875_DungeonForestLH, and Xpl300_Stronghold.

The Veithurgard acceptance fixture remains exact:

- `raven_642d0d164af0a5d4076e77933c549a5d` -> false
- `raven_c945cb53465b58decfcbd4a221cb5326` -> true
- `raven_e32f7bab42fd7298890f6aa56a734562` -> true

## Remaining 11 are coverage absence, not identity failure

The unresolved catalogue rows are exactly those whose Raven-bearing WAD is absent from this 425-record staged snapshot:

- `foot250_chiselarena.wad` - 1 Raven
- `for260_chiseldungeon.wad` - 1 Raven
- `xpl100_httk.wad` - 3 Ravens
- `xpl150_httktemple.wad` - 1 Raven
- `xpl170_httkcaver.wad` - 1 Raven
- `xpl450_huldramines.wad` - 1 Raven
- `xpl475_huldramineslh.wad` - 1 Raven
- `peak205_chiselarena.wad` - 1 Raven
- `stn110_chiselarena.wad` - 1 Raven

Total: 9 absent WADs / 11 Ravens.

Because absence is not authoritative evidence of `ravenKilled=false`, these 11 remain unknown. Do not default them alive for an existing save.

The identity problem itself is solved: the generated catalogue has 53 unique serialized payloads and the live-covered 42 all match exactly.

## Next authority problem

Find the authoritative persisted checkpoint/save state for WADs that are not represented in the current staged WAD table. The next research must distinguish:

1. WAD never materialised in this save/checkpoint, where native semantics may prove default state;
2. WAD persisted elsewhere because it is currently unstaged/unloaded;
3. stale physical-save-ring state, which must not be treated as current authority without a freshness proof.

Preferred next route: trace the staged-table population/lookup path from the known `0x82C820 / 0x82CC0C / 0x82B250` checkpoint machinery to identify the backing authoritative store or miss path used when a WAD key is absent from the 425-record table. Preserve the no-write/read-only requirement.


---

# Addendum 2026-09-21 - 42-state acceptance complete; staged WAD binding lifecycle probe added

The corrected identity pipeline is now accepted against the archived live checkpoint capture:

- 42 exact Raven states resolved;
- 27 killed / 15 alive;
- 30 Raven-bearing carriers;
- zero ambiguity;
- zero unmatched Raven state keys;
- remaining 11 correspond exactly to 9 Raven WADs absent from the current staged table.

The remaining authority problem is therefore WAD coverage, not identity.

Static evidence from the existing staged writer shows `0x6687F0` iterates the game's global WAD object array and calls `0x82C820` only for eligible runtime WAD objects. `0x82C820` serializes through the staged-record index already stored at `WAD+0xEE18`; it does not assign that binding itself.

The next proof target is the lifecycle of `WAD+0xEE18`: where the staged-record index is bound, cleared, retained, or reconstructed. This determines whether a WAD absent from the 425-record staged table can be proven never-persisted/default, or whether its state was retired to another backing store.

New tooling:

- `0ba903293669d4ead0ea3849449a4c95760f238a` - `trace-staged-wad-record-binding.py`
- `ed767f650e38c97f7645a0b892fe323a6c597c2c` - static trace-and-push runner

The tracer enumerates all indexed memory references to `+/-0xEE18` and neighbouring WAD fields, classifies direct writes to `+0xEE18`, captures full enclosing functions, caller/callee relationships, and overlap with the staged-record globals `0x22C696C / 0x22C7170 / 0x22C7194 / 0x22C6938 / 0x22C6940`.

No process or save access is used.


---

# Addendum 2026-09-21 - first WAD binding probe exposed index gap; raw executable scan substituted

The first `WAD+0xEE18` lifecycle run committed as `3e4d80bef5eb1607785bf6ad2e506e6990a07d66` completed successfully but returned zero structure-displacement hits:

```text
related_refs=0 exact_binding_refs=0 writes=0 reads=0
```

This is a tracer/index limitation, not evidence that the field is unused. Earlier full disassembly already proves multiple reads of `WAD+0xEE18` at sites such as `0x23FED2`, `0x673BAF`, `0x6787CA`, `0x82B3A1`, `0x82C871`, and `0x82CC19`.

Cause: the existing SQLite research index does not reliably retain these large structure displacements in `mem_refs`.

Fix:

- `885e3f380aa3465c76f192245c547452186c7d5e` - tracer now scans the executable `.text` bytes for the signed little-endian disp32 encodings of `+/-0xEE18` and neighbouring WAD fields, maps each occurrence to the enclosing indexed function, then validates the actual Capstone memory operands before classifying reads/writes.
- `99d692b628b02cb41cf72b7f1c6fcbd24fd45ba6` - cleanup commit.

This removes the `mem_refs` dependency while keeping the analysis fully static/read-only.


---

# Addendum 2026-09-21 - WAD binding/unbinding semantics proven; record-count lifecycle tracer added

Corrected raw-executable binding evidence commit: `cb0612192ea34ac900278fc3de036298bc41e0eb`.

The fixed tracer found 15 exact `WAD+0xEE18` references:

- 2 writes;
- 13 reads.

The two writes have distinct semantics.

## Bind path: 0x673A30 / write at 0x673BEC

`0x673A30` is called from restore/load function `0x673D00` at `0x67421C`.

When the runtime WAD's `+0xEE18` binding is negative, it computes the current staged-record index from the record pointer relative to `0x22C7170` with stride `0xA8`, then writes that index into `WAD+0xEE18`:

```text
0x673BAF cmp word ptr [rdi+0xEE18],0
0x673BB7 jge ...
0x673BC4 lea rax,[record_base]
...
0x673BEC mov word ptr [rdi+0xEE18],dx
```

Therefore `+0xEE18` is the live WAD -> staged-record index binding.

## Unbind path: 0x676CC0 / write at 0x676F76

`0x676FB0` iterates staged records and calls `0x676CC0` at `0x6770A6` for records needing unload/cleanup.

`0x676CC0` resolves the runtime WAD from the staged record's `+0x28` native slot, performs WAD cleanup, and when its unload flag is true does:

```text
0x676F6E mov ecx,-1
0x676F73 mov dword ptr [record+0x28],ecx
0x676F76 mov word ptr [WAD+0xEE18],cx
```

So normal WAD unload clears both live associations to `-1` but does **not** delete or compact the staged `0xA8` record itself.

This proves the staged table retains a record independently of the runtime WAD binding.

## Record-count mutation evidence already visible

Two writer functions are visible in the same report:

- `0x67B830` searches staged record names and, if no existing name matches, increments `record_count` at `0x67BA68`, initialises a new `0xA8` record, copies the name into `+0x84`, and derives the record key at `+0x24`. This is an append/create path.
- `0x671AD0` can reset `record_count` at `0x671C3F`; depending on its full-reset mode it clears every record structure and may set the whole count to zero. This is a global table reset/reinitialisation path, not an individual WAD removal path.

A final static proof is still required because the global has many other readers/references and some `mov` sites may also be writes.

New tooling:

- `891e65880d4973100d0c60c6b116d08f58908f25` - all-writer `record_count` lifecycle tracer;
- `f8f4347ad6f9fd3bc230b78a7cb153d2021da62c` - writer-ID fix;
- `a99b85659258c29b60dea083c7877c0a7d211160` - static trace-and-push runner.

The next pass classifies every RIP-relative reference to `0x22C696C` with Capstone operand access bits and emits the full function for every actual writer. Acceptance condition: no individual delete/compact writer. If all writes are append, restore/rebuild, or whole-table reset, then an absent WAD key in a live current staged checkpoint can be treated as having no persisted custom Lua state; for Raven `ravenKilled`, whose script default is false and whose kill transition writes true before checkpoint persistence, that closes the absent-WAD authority case without guessing.


---

# Addendum 2026-09-21 - staged record absence semantics closed

Record-count lifecycle evidence commit: `826b4f36250d24557d31b6b1dadc5434bcc4ab61`.

The tracer found exactly 7 native writes to the proven staged WAD `record_count` global at RVA `0x22C696C`. All seven are now classified:

1. `0x671C3F` in `0x671AD0` - whole-table reset/reinitialisation. It iterates all existing `0xA8` records, clears their fields, and conditionally sets the entire count to zero. It is not an individual WAD removal path.
2. `0x673165` in `0x6730C0` - append/create. It searches existing record names; when not found and creation is allowed it uses the old count as the new index, increments the count, and initialises one new `0xA8` record.
3. `0x67BA68` in `0x67B830` - append/create by name. It searches all existing names and increments count only when no match exists, then initialises one new staged record.
4. `0x67CC12` in `0x67CC00` - subsystem startup initialisation; explicitly writes zero before allocating backing storage.
5. `0x68204D` in `0x682020` - subsystem/global startup initialisation; explicitly writes zero before broad engine allocation/initialisation.
6. `0x82CFAC` in `0x82CF00` - restore/rebuild from serialized input. The function reads a serialized record count, reconstructs that many `0xA8` records/payload slices, then writes the deserialized count.
7. `0x82D251` in the same `0x82CF00` restore path - append/create for a runtime WAD name not present in the restored staged list. It increments the count and initialises one new record.

There is no decrement, remove-one, swap-delete, compaction, or per-WAD count reduction anywhere in the executable.

Combined with the already-proven normal unload path `0x676CC0`, which writes `record+0x28=-1` and `WAD+0xEE18=-1` while leaving the staged record allocated, this closes staged-record lifetime semantics:

- once a WAD has a staged record in the current checkpoint lineage, normal unload does not make that named record disappear;
- an individual record cannot later be deleted from the staged table;
- absence of a Raven WAD name from the current staged table therefore means no persisted custom Lua state exists for that WAD in this staged checkpoint lineage;
- Raven `ravenKilled` defaults to false in the script and only becomes true on the kill transition before checkpoint persistence;
- therefore absent Raven WAD => authoritative `ravenKilled=false` for this staged-state model.

Implementation commits:

- `8d4b02ac20aecad950d2543061315906a5f17b4c` - offline replay now classifies absent Raven WADs as `false` with authority `native_absent_wad_default_false`, while present-but-undecodable WADs remain unknown/fail-closed.
- `2542f64f18bf40ca4e77ff05f9ec51fdbc36d02b` - live read-only staged observer uses the same rule.

Expected offline acceptance on the existing `20260921-060345-c2c9bcc1` capture:

```text
candidate_state_count=53
unknown_count=0
absence_default_false_count=11
```

This closes the 53-Raven staged authority model. Overall mod `production_ready` remains false until this complete authority result is wired into the runtime map path and validated against fresh-save, old-save, map-reopen, immediate-kill, and restore fixtures.


---

# Addendum 2026-09-21 - complete 53-Raven staged authority accepted; native Lua delivery probe prepared

Offline acceptance commit: `24a0c7bc159ecdfdbe7941aca779485eb11e681a`.

The existing archived live staged snapshot now replays as:

```text
candidate_state_count=53
unknown_count=0
absence_default_false_count=11
production_ready=false
```

This closes the complete 53-Raven staged authority model:

- 42 Raven states come from explicit decoded `ravenKilled` rows in Channel A;
- 11 Raven states come from the proven native absent-WAD default-false rule;
- zero Raven state remains unknown;
- the Veithurgard `false,true,true` fixture remains exact.

`production_ready` remains false only because this complete authority result still needs to be delivered into the in-game map runtime and validated end-to-end.

## Runtime delivery route

The previous runtime capability capture proves the game's Lua environment has:

```text
package=table
package.loadlib=true
io=nil
os=nil
```

The GoW Script Loader source also shows it executes the game's own Lua VM directly. Therefore the preferred runtime architecture is a small in-process, read-only Lua C module loaded with `package.loadlib`, rather than an external Python sidecar or polling process.

The final native module is intended to:

1. read the proven staged WAD table directly from the current GoW process;
2. decode the complete 53-Raven state vector read-only;
3. return booleans to Lua;
4. let the existing map runtime atomically replace Raven state before map-icon synchronisation;
5. leave the already-proven loaded-Raven `ravenKilled` event path unchanged for immediate kill/restore updates.

No save/progression writes are introduced.

## Native Lua ABI probe

Before porting the decoder, a deliberately minimal bridge probe was added to prove the actual Lua C-function ABI and DLL loading path inside the game.

Commits:

- `2e646bbbd58ad3a0473810e2414d0c067b5ca66b` - native probe C source.
- `89bd06a9cf47bdb37fe42d6a2faa9436104b33b1` - compiled import-free Windows x64 probe DLL.
- `99c6fc5f4b79bd62f670557f6e44fb34d3d9ccc9` - Lua `package.loadlib` ABI validation script.
- `207bda08a35a015f7e00d9c2a1a86d50109a362a` - self-restoring runtime probe runner.

Files:

- `native/v0.10.5/completionist_raven_authority_probe.c`
- `native/v0.10.5/completionist_raven_authority_probe.dll`
- `tools/v0.10.5/raven-native-bridge-probe.lua`
- `tools/v0.10.5/run-raven-native-bridge-probe-and-push.ps1`

Probe DLL SHA-256:

```text
79afab868a49776c6cd6e7c2bce8efa64a8f8edecb4eb664e7ae923f0da17fa5
```

The DLL has no imported runtime dependency and exports:

- `completionist_raven_probe_a`
- `completionist_raven_probe_b`
- `completionist_raven_probe_c`
- `DllMain`

The three probe functions return success plus 18, 18, and 17 Lua booleans respectively, for exactly 53 test booleans. The Lua probe validates result count, type, and a fixed alternating pattern.

The runner temporarily appends the Lua probe to installed `mapmenu.lua`, copies the test DLL under `mods\\completionist_map`, launches the game, captures only the fresh loader-log lines, then restores `mapmenu.lua` byte-for-byte and restores/removes the DLL. No save needs to be loaded.

Expected acceptance marker:

```text
[CompletionistRavenNativeBridgeProbe] BRIDGE_OK ... chunks=18,18,17 total=53 ...
result=RAVEN_NATIVE_LUA_BRIDGE_PROVEN
```

If this passes, the next implementation step is to replace the fixed test booleans with the proven staged Raven authority decoder inside the same native bridge and wire the resulting 53-state snapshot into map-open synchronisation.


## Native bridge probe preflight correction

First local run produced capture commit `9a42157` and correctly stopped before game launch with:

```text
RAVEN_NATIVE_BRIDGE_PROBE_FAILED: Bridge probe DLL SHA mismatch: 79afab868a49776c6cd6e7c2bce8efa64a8f8edecb4eb664e7ae923f0da17fa5
```

The runner had accidentally pinned a stale pre-commit DLL SHA (`ba66ad78...`) instead of the SHA of the DLL actually committed to Git. No GoW process was launched and no game/save/progression writes occurred.

Correction commit:

- `9104df8116b34db216da232218a8ab0927482a59` - pin the committed probe DLL SHA in the runner.

Next step: rerun the same self-restoring native bridge probe. It should now pass preflight, launch GoW, and wait for a main-menu launch/exit so the Lua C ABI evidence can be captured and pushed.


## Native bridge probe PowerShell newline correction

Second local run produced capture commit `317bfa2e033ed4b3764789f428fe0fadeceec52c` and again stopped before game launch.

Failure:

```text
Cannot convert argument "newChar" ... for "Replace" to type "System.Char"
```

Cause: PowerShell selected the `String.Replace(char,char)` overload for `$probeText.Replace([char]10, [Environment]::NewLine)`, but Windows CRLF is a two-character string.

Correction commit:

- `be48b481932405f66b25adad3669c3647d8e2777` - normalise CRLF/CR/LF using string replacements before appending the Lua probe.

Safety evidence from the failed run:

```text
game_launched=false
mapmenu_restored=true
bridge_dll_restored=true
probe_process_memory_writes=false
probe_save_writes=false
probe_progression_writes=false
probe_game_file_persistence=false
```

Next step: rerun the same self-restoring bridge probe.


## Native bridge probe result - package.loadlib route CLOSED

Runtime capture commit:

- `6eea3834d095e5d2f5429dc8b007dc0bea0ea8db`
- evidence: `archive/field-logs/runtime-captures/raven-native-bridge-probe-20260921-080821/`

The corrected runner reached GoW successfully and the injected Lua probe executed. The decisive loader-log line was:

```text
[CompletionistRavenNativeBridgeProbe] BRIDGE_FAILED phase=load ... dynamic libraries not enabled; check your Lua installation
```

Safety/restore result:

```text
game_launched=true
mapmenu_exact_restore=True
bridge_dll_restored=true
probe_process_memory_writes=false
probe_save_writes=false
probe_progression_writes=false
probe_game_file_persistence=false
```

Conclusion:

- `package.loadlib` is exposed as a Lua function but the compiled Lua runtime has dynamic-library loading disabled.
- Do not repeat `package.loadlib` path/probing.
- The previously proposed standalone native Lua C DLL bridge is closed.

### Upstream Script Loader review

The installed Script Loader is Nukem9's `godofwar-gameplay-tweaks` `version.dll`. Upstream source shows that it directly hooks GoW's Lua chunk loader and related engine functions, but it exposes no third-party native plugin ABI. Upstream README also explicitly states `No license provided. TBD.`, so Completionist Map should not plan to redistribute a modified Script Loader binary.

A locally built loader fork may remain useful as a development-only proof, but not as the preferred public release architecture.

### New Lua-only bridge candidate: VFSExec

The exhaustive native Lua registration catalogue already contains the UI/global VFS helpers:

```text
VFSExec          entry=0x11CA640 inferred handler cluster start=0x84AB50
VFSGetEnumIndex  entry=0x11CA660 fn=0x84AB60
VFSGetEnumName   entry=0x11CA680 fn=0x84AB70
VFSGetFloat      entry=0x11CA6A0 fn=0x84AB90
VFSGetInt        entry=0x11CA6C0 fn=0x84ABB0
VFSSetFloat      entry=0x11CA6E0
VFSSetInt        entry=0x11CA700
```

Because `VFSExec` is native and already callable from the game's Lua surface, it must be resolved before considering a custom loader fork. If it accepts a disk/VFS-backed file or executable command payload, it could provide the missing read-only authority-delivery bridge while keeping Completionist Map an ordinary Script Loader Lua mod.

Static read-only tracer added:

- `854ef1045fa2cbd6c97346de1c95f9e5526c363c` - `tools/v0.10.5/trace-lua-vfs-exec-bridge.py`
- `98b8fdc2332ca51ebbb87fa292ebdf3a2b1d44b7` - `tools/v0.10.5/trace-lua-vfs-exec-bridge-and-push.ps1`

Next step: run only this static tracer with GoW closed. No save is opened and the game is not launched.


## Lua VFSExec static result - direct file bridge rejected

Evidence commit:

- `8fef5feaaf3296bd6e650a3f58fcaf579429a8c2`
- evidence: `archive/field-logs/source-scans/lua-vfs-exec-bridge-20260921-081523/`

The static tracer completed with:

```text
LUA_VFS_EXEC_BRIDGE_TRACE_COMPLETE functions=2
save_opened=false save_written=false progression_written=false game_launched=false
```

The registration mapping resolves `VFSExec` to function `0x84AB40..0x84AB55` rather than the earlier inferred interior address `0x84AB50`.

Its complete body is only:

```text
0x84AB40 sub rsp,0x28
0x84AB44 mov dl,1
0x84AB46 call 0x84FCC0
0x84AB4B mov eax,1
0x84AB50 add rsp,0x28
0x84AB54 ret
```

Shared helper `0x84FCC0`:

- retrieves a string-like argument from the caller/UI state;
- normalises ASCII lowercase letters to uppercase while hashing the string;
- uses multiplier `0x401` and xor/shift mixing to derive a command/key hash;
- calls native hash/lookup helper `0x431B90`;
- searches a global array of registered values/commands;
- then dispatches through a global object's virtual method `+0x98`;
- the sibling wrapper at `0x84AB20` calls the same helper with the boolean flag cleared.

No direct file-open/read primitive, path handling, save-file access, Lua source loading, or arbitrary disk payload read is visible in this path.

Conclusion:

- reject the assumption that `VFSExec` itself is a generic Virtual File System file-read/execute bridge;
- it is a hash-based registered VFS command/value dispatcher;
- it is only useful if an already-registered VFS command exposes the staged checkpoint authority we need;
- do not build a runtime file bridge around `VFSExec` without first proving such a registered command exists.

Next productive step: statically resolve the VFS registry behind `0x84FCC0`, identify the registered command/value set and the `+0x98` dispatch implementation, and search specifically for checkpoint/save/staged-WAD related entries. This remains static/read-only. If no relevant authority command exists, close the VFS route and return to the proven staged-record/native-owner path rather than modifying or redistributing Script Loader.


## VFS registry resolver tooling added

The handoff was re-read after recording the `VFSExec` result. The next step remains exactly the bounded static registry proof described above.

New tooling:

- `0d83eb491d10176e983a958e1d9ef2c4f29ee7a4` - `tools/v0.10.5/trace-lua-vfs-registry.py`
- `89a05a30c54c3a1344b4abd480a6dfd074fcc37d` - `tools/v0.10.5/trace-lua-vfs-registry-and-push.ps1`

The tracer is static/read-only and targets:

```text
shared helper      0x84FCC0
hash lookup helper 0x431B90
registry count     0x2D481B4
registry entries   0x504C0A0
dispatcher pointer 0x123B680
```

It:

1. finds every code reference to the three VFS registry/dispatcher globals;
2. finds all direct callers of the shared helper and hash helper;
3. emits full enclosing functions plus one-hop callers/callees;
4. captures printable RIP-relative strings from those functions;
5. scans non-executable image data for VFS/save/checkpoint/WAD/Lua/restore/slot/state/pickle/Raven labels;
6. performs no process attach, game launch, save access, save write, progression write, or game-file write.

Acceptance decision after this run:

- if a registered VFS command/value clearly reaches checkpoint/save/staged-WAD authority, follow only that concrete route;
- otherwise close VFS as a delivery route and return to the proven native staged-record owner path.

Next action: run `trace-lua-vfs-registry-and-push.ps1` with GoW closed.


## VFS registry trace first run - PE section schema correction

Failed evidence commit:

- `5f9ce0404e13965704a6ca6350fa79b61c15a656`
- evidence directory: `archive/field-logs/source-scans/lua-vfs-registry-20260921-082511/`

Failure:

```text
KeyError: 'raw_ptr'
```

The failure occurred only in the tracer's non-executable section string-scan stage. It did not launch or attach to GoW and did not access or write saves/progression.

Cause:

- the new tracer assumed PE section dictionary keys `raw_ptr` / `raw_size`;
- the repository's proven PE helper actually exposes `raw` / `rawsize`.

Correction:

- `351c05ae0b2b851de5cab23e27a7a691759f1466` - update the VFS registry tracer to use the existing PE helper schema and clamp the scan range to the executable byte length.

Corrected code now uses:

```python
start=sec["raw"]
end=min(len(pe.data), start+sec["rawsize"])
```

The research question is unchanged. Next action remains the same bounded static VFS registry trace with GoW closed.


## VFS registry trace succeeded - raw report requires compaction

Evidence commit:

- `d697742b8860d3ace32b2aca981f69f7a8faf58a`
- evidence: `archive/field-logs/source-scans/lua-vfs-registry-20260921-083114/`

The corrected static trace completed successfully:

```text
LUA_VFS_REGISTRY_TRACE_COMPLETE
vfs_dispatcher_ptr_refs=766
vfs_registry_entries_refs=8
vfs_registry_count_refs=12
save_opened=false
save_written=false
progression_written=false
game_launched=false
```

Raw evidence sizes are unusually large:

- `report.txt` ~17.8 MB
- `report.json` ~81.6 MB

This happened because the broad one-hop selection pulled in hundreds of functions via the dispatcher global. The raw evidence is preserved, but it should not be repeated or used as the normal review surface.

The meaningful result so far is:

- the VFS registry is real and has a small number of direct entry/count references;
- the dispatcher pointer is shared very broadly and is not useful as an unconstrained selection root;
- the next step is to compact the already-captured report, not rerun the executable scan.

Next target: extract only:
1. the 8 `vfs_registry_entries` references;
2. the 12 `vfs_registry_count` references;
3. their enclosing functions and direct calls/strings;
4. all writers to entries/count;
5. direct callers of `0x84FCC0`;
6. checkpoint/save/WAD/restore/state/pickle/Raven strings only when they occur in those narrowly relevant functions.

Do not regenerate the broad VFS registry report.


## VFS registry compact-review tooling added

The handoff was re-read after the successful raw VFS-registry capture. The next step remains evidence compaction only; do not rerun the broad executable scan.

New tooling:

- `886d6e03e35bb7f08b01cea1ad16d23da4693dd4` - `tools/v0.10.5/compact-lua-vfs-registry-report.py`
- `a7bb0d2375288207e5dcc387c26870c206a1532d` - `tools/v0.10.5/compact-lua-vfs-registry-report-and-push.ps1`

The compactor consumes the already-generated `report.json` from the latest completed `lua-vfs-registry-*` evidence directory and emits only:

- all direct `vfs_registry_entries` references, split into reads/writes;
- all direct `vfs_registry_count` references, split into reads/writes;
- direct callers of the shared VFS helper `0x84FCC0`;
- the enclosing narrow functions;
- their direct calls/callers;
- only checkpoint/save/WAD/Lua/restore/slot/state/pickle/Raven strings in those functions.

It explicitly does not rescan `GoW.exe`, launch GoW, attach to a process, open a save, or write progression/game files.

Next action: run only `compact-lua-vfs-registry-report-and-push.ps1`. After its compact summary is pushed, decide whether VFS has a concrete authority-bearing command. If not, close VFS and return to the proven staged-record/native-owner path.


## VFS registry compact result - VFS delivery route CLOSED

Compact evidence commit:

- `801c85d543e7686d2799b82397cc99f812d448c1`
- summary: `archive/field-logs/source-scans/lua-vfs-registry-20260921-083114/summary.txt`

The existing broad capture was compacted without rescanning `GoW.exe`:

```text
selected_functions=10
vfs_registry_entries_refs=8
vfs_registry_entries_writes=0
vfs_registry_count_refs=12
vfs_registry_count_writes=7
vfs_shared_helper_callers=3
gow_exe_rescanned=false
save_opened=false
save_written=false
progression_written=false
game_launched=false
```

The three direct callers of shared helper `0x84FCC0` are only:

- `0x84AB20` - sibling Lua VFS wrapper;
- `0x84AB40` - `VFSExec`;
- `0x84FCC0` itself through its internal loop/back-edge classification.

The ten narrowly selected functions that touch the registry entry/count globals contain no relevant save/checkpoint/WAD/Lua-restore/slot/state/pickle/Raven strings. The registry/count mutators are generic hash-registry lifecycle functions; no concrete VFS command/value that exposes staged checkpoint authority was identified.

Conclusion:

- close VFS as an authority-delivery route;
- do not run more broad VFS registry scans;
- do not build Completionist Map around `VFSExec`;
- `package.loadlib` is already closed separately;
- do not plan to redistribute a modified unlicensed Script Loader.

Return to the proven staged-record/native-owner path and look for an **already exposed native Lua binding** that can query or resolve the staged GameObject/persisted state directly, rather than inventing a new native loading mechanism. The complete 53-Raven authority model itself remains solved and accepted; only runtime delivery remains open.


## Persisted Lua binding proof queued

After closing VFS, the handoff was re-read and the repository's existing Lua API inventories were checked before adding any new scan.

Already-known registered read/query candidates:

```text
ResolveGameObject  0x84F750
GetRefBool         0x845700
GetRefFloat        0x8456E0
GetRefInt          0x8456C0
GetRefString       0x8456A0
LoadCheck          0x84E880
```

These are the strongest remaining built-in native Lua candidates because they may resolve references or state without requiring a standalone DLL/plugin. The generic GameObject Lua API inventory already exists and should not be repeated.

New bounded static tooling:

- `4d1baa5f7d17b9cde08758bfb59971669093ae2d` - `tools/v0.10.5/trace-lua-persisted-reference-bindings.py`
- `2e4398481befcc8afd8c5442d8482f0c0905393d` - `tools/v0.10.5/trace-lua-persisted-reference-bindings-and-push.ps1`

The tracer examines only those six handlers plus one-hop direct callers/callees and tests for intersection with the already-proven staged authority surface:

```text
staged globals:
  0x22C696C record_count
  0x22C7170 record_base
  0x22C7194 record end/cursor
  0x22C6938 / 0x22C6940 staged auxiliaries

WAD binding:
  +0xEE18

known staged functions:
  0x82C820
  0x82CC0C
  0x82B250
  0x82CF00
  0x673A30
  0x673D00
  0x676CC0
  0x67B830
  0x671AD0
```

Acceptance decision:

- any direct staged-global access, `WAD+0xEE18` access, or call into the proven staged owner/restore functions makes that native Lua binding a concrete bridge candidate;
- if all six are disjoint from the staged authority surface, close this built-in binding set and continue from the native staged owner itself rather than probing unrelated Lua APIs.

The trace is fully static/read-only and requires GoW closed.


## Persisted Lua binding trace result - LoadCheck/ResolveGameObject closed, GetRef exact handlers still unresolved

Evidence commit:

- `01ab42379a738c6cdd02aede7fa65a7b2933390a`
- evidence: `archive/field-logs/source-scans/lua-persisted-reference-bindings-20260921-084254/`

The bounded static trace completed safely:

```text
LUA_PERSISTED_REFERENCE_BINDINGS_TRACE_COMPLETE
selected_functions=4
any_staged_touch=false
save_opened=false
save_written=false
progression_written=false
game_launched=false
```

Resolved functions:

```text
0x84E880..0x84E8F5  LoadCheck
0x84F750..0x84F7C9  ResolveGameObject
0x6BFBF0..0x6BFCC3  LoadCheck callee
0x67C190..0x67C1B3  LoadCheck callee
```

None of those four functions:

- references the proven staged globals `0x22C696C / 0x22C7170 / 0x22C7194 / 0x22C6938 / 0x22C6940`;
- accesses `WAD+0xEE18`;
- calls the known staged owner/restore functions;
- contains a direct staged-authority bridge.

Therefore `LoadCheck` and `ResolveGameObject` are closed as direct Raven staged-authority delivery routes.

Important limitation: the registration catalogue's exact `GetRef*` addresses:

```text
GetRefString 0x8456A0
GetRefInt    0x8456C0
GetRefFloat  0x8456E0
GetRefBool   0x845700
```

did not map to separate runtime-function records in the PE exception-function table, so the first tracer did **not** actually disassemble or prove their implementations. Do not close `GetRef*` yet.

Next step: disassemble fixed byte windows at those exact four RVAs independent of runtime-function boundaries, follow their direct targets narrowly, and test those targets against the proven staged globals/functions. This is the final unresolved part of this built-in binding set.


## Exact GetRef handler proof queued

The handoff was re-read after the persisted-binding trace. The only unresolved part of that built-in Lua binding set is now the four exact `GetRef*` handlers, because those RVAs are not represented as separate PE exception/runtime-function records.

New tooling:

- `f80db270588e1eb35a4511a2bb1c6cbe2c719af8` - `tools/v0.10.5/trace-lua-getref-exact-handlers.py`
- `510203ede1920e2b477f9581ed7f08566fc2affb` - `tools/v0.10.5/trace-lua-getref-exact-handlers-and-push.ps1`

Exact entrypoints:

```text
GetRefString 0x8456A0
GetRefInt    0x8456C0
GetRefFloat  0x8456E0
GetRefBool   0x845700
```

The tracer:

1. disassembles fixed windows at those exact RVAs without relying on runtime-function boundaries;
2. stops each exact entry window at `ret` to avoid bleeding into adjacent wrappers;
3. follows only direct `call/jmp` targets to depth 2;
4. checks all visited code for the proven staged globals, `WAD+0xEE18`, and known staged owner/restore functions;
5. records exact disassembly and direct targets for final semantic classification.

Acceptance decision:

- if any `GetRef*` path intersects the staged authority surface, preserve it as the concrete built-in Lua bridge candidate;
- if all four remain disjoint through the narrow direct-target trace, close the entire `ResolveGameObject / GetRef* / LoadCheck` built-in binding set and move to the native staged owner itself.

Static/read-only only; GoW must be closed.


## Exact GetRef result - built-in persisted binding set CLOSED

Evidence commit:

- `badd4fa0bab4087239ab5b8974f303e81a3364dd`
- evidence: `archive/field-logs/source-scans/lua-getref-exact-20260921-091651/`

The exact fixed-window trace completed safely:

```text
LUA_GETREF_EXACT_TRACE_COMPLETE
nodes=4
any_staged_touch=false
save_opened=false
save_written=false
progression_written=false
game_launched=false
```

Exact handlers:

```text
GetRefString 0x8456A0
  cmp [rcx+0x28],0
  eax=3
  if non-null: zero qword [rdx]
  ret

GetRefInt 0x8456C0
  cmp [rcx+0x28],0
  eax=1
  if non-null: zero qword [rdx]
  ret

GetRefFloat 0x8456E0
  eax=0
  cmp [rcx+0x28],rax
  if non-null: zero qword [rdx]
  ret

GetRefBool 0x845700
  cmp [rcx+0x28],0
  eax=2
  if non-null: zero qword [rdx]
  ret
```

They have:

- no direct calls or jumps outside their tiny wrappers;
- no staged-global accesses;
- no `WAD+0xEE18` accesses;
- no known staged-owner/restore calls.

These functions are type/default/ref-value helpers, not checkpoint/save/staged authority readers.

Conclusion:

- close `GetRefString / GetRefInt / GetRefFloat / GetRefBool` as Raven authority bridges;
- together with the previous proof, close the full `ResolveGameObject / GetRef* / LoadCheck` built-in persisted-binding candidate set;
- do not probe these APIs again.

Next route: start from the **proven staged owner itself** and trace reverse native callers toward the exhaustive Lua registration handler set. This is preferable to guessing more API names. The exact question is whether any already-registered Lua handler reaches the staged record owner through a short direct native call chain. If yes, follow only that concrete handler. If no, record that there is no short direct built-in Lua bridge and move to a release architecture decision.


## Staged owner reverse-to-Lua proof queued

The handoff was re-read after closing the exact `GetRef*` handlers. No prior reverse-reachability proof from the staged owner to the exhaustive Lua registration handler set was found, so the next scan is new rather than duplicate work.

New tooling:

- `ce3f004b5c276de97e75d80a3da84a8b9497fe38` - `tools/v0.10.5/trace-staged-owner-reverse-lua-reachability.py`
- `1231baf2273c0e9cbad813e86bb46ab37e54c711` - `tools/v0.10.5/trace-staged-owner-reverse-lua-reachability-and-push.ps1`

The tracer:

1. parses the already-generated exhaustive native Lua registration catalogue;
2. statically disassembles GoW runtime functions and builds direct `call/jmp` reverse edges;
3. seeds from the proven staged owner/restore functions plus every function that directly references the proven staged globals;
4. walks native callers upward to bounded depth 4;
5. intersects every visited function with registered Lua handler functions;
6. reports only concrete staged-owner -> caller -> registered-Lua paths plus small aggregate frontier counts.

Root surface includes:

```text
0x82C820 staged lookup/writer
0x82CC0C staged related
0x82B250 staged related
0x82CF00 staged restore/rebuild
0x673A30 WAD bind
0x673D00 WAD restore/load
0x676CC0 WAD unbind
0x67B830 record append
0x671AD0 record reset
0x6687F0 staged WAD writer
plus direct readers/writers of:
  0x22C696C
  0x22C7170
  0x22C7194
  0x22C6938
  0x22C6940
```

Acceptance decision:

- if one or more registered Lua handlers are reachable within this bounded direct native call graph, follow only the shortest concrete path(s) and classify whether they can expose read-only staged Raven authority;
- if no registered Lua handler is reachable, record that there is no short direct built-in Lua bridge from the staged owner and move to the release-architecture decision rather than guessing additional API names.

The tracer is static/read-only and requires GoW closed.


## Reverse staged-owner trace result - SaveGame path found; two read handlers need semantic classification

Evidence commit:

- `539220129f5fb4cc8bb03921972947f9e3156a41`
- evidence: `archive/field-logs/source-scans/staged-owner-reverse-lua-20260921-092551/`

The bounded reverse trace completed safely:

```text
roots=80
reverse_nodes_visited=247
lua_paths=10
max_depth=4
save_opened=false
save_written=false
progression_written=false
game_launched=false
```

Concrete Lua intersections:

```text
depth 0:
  GetAppMasterVersion  handler 0x783880
    directly references 0x22C7170 (record_base)

  GetLevelId           handler 0x847F10
    directly references 0x22C7170 (record_base)
    directly references 0x22C696C (record_count)

write-side path:
  SaveGame 0x84F1C0
    -> 0x66B650
    -> 0x6687F0 staged WAD writer
    -> 0x82C820 staged record writer
```

This proves the staged authority is directly integrated into the native save pipeline.

However:

- `SaveGame` is a write-oriented route and cannot be used by Completionist Map because the runtime authority reader must not trigger save/progression writes.
- Presence of `GetAppMasterVersion` and `GetLevelId` on staged globals does not yet prove they are generic readers; they may be fixed metadata accessors over the same save/checkpoint owner.

Therefore do **not** claim a usable Lua bridge yet.

Next step: statically disassemble only `GetAppMasterVersion 0x783880`, `GetLevelId 0x847F10`, their direct callees, and `0x66B650` for context. Classify whether either read handler can select arbitrary staged records/custom userdata or only returns one fixed metadata value. If both are fixed metadata-only, close the short direct built-in Lua bridge route and move to release architecture.


## Read-side staged Lua intersection classification queued

The handoff was re-read after the reverse staged-owner trace. That trace found ten registered Lua intersections, but only two are read-looking:

```text
GetAppMasterVersion 0x783880
GetLevelId          0x847F10
```

The remaining concrete route is `SaveGame 0x84F1C0 -> 0x66B650 -> staged serialization`, which is write-side and cannot be used by the mod.

New tooling:

- `ff1fb8f12f676d362fa8d9a1907c0997da7ac5e4` - `tools/v0.10.5/trace-lua-read-staged-intersections.py`
- `dd4cb0f4fab7208a6b5126b8423524d069b94b8e` - `tools/v0.10.5/trace-lua-read-staged-intersections-and-push.ps1`

The classifier statically disassembles:

```text
GetAppMasterVersion 0x783880
GetLevelId          0x847F10
0x66B650            save-pipeline context
```

plus only their direct callees.

It records:

- exact disassembly;
- direct calls/jumps;
- exact staged-global accesses;
- RIP-relative strings/globals;
- argument-derived memory accesses through `rcx/rdx/r8/r9`.

Acceptance decision:

- if either read handler accepts/selects a staged record/key and can return arbitrary/custom persisted data without writes, preserve it as the built-in authority bridge;
- if both only return fixed metadata fields, close the short direct built-in Lua bridge route;
- `SaveGame` remains evidence of pipeline integration only and must not be invoked by Completionist Map.

Static/read-only only; GoW must be closed.


## Read-side staged Lua result - short direct built-in Lua bridge CLOSED

Evidence commit:

- `6da461ded95a1957331bc05abd8c65f112407842`
- evidence: `archive/field-logs/source-scans/lua-read-staged-intersections-20260921-092909/`

The classifier completed safely:

```text
LUA_READ_STAGED_INTERSECTION_TRACE_COMPLETE nodes=17
save_opened=false
save_written=false
progression_written=false
game_launched=false
```

### GetLevelId `0x847F10`

This handler:

1. derives one WAD/name string from its Lua/UI call context;
2. scans the staged `0xA8` records by comparing against record name storage at `record+0x84`;
3. on a match returns only `record+0x24`, the fixed WAD/level ID;
4. otherwise returns `-1`.

It cannot select/read Channel A, Channel B, custom-userdata bytes, or `ravenKilled`.

### GetAppMasterVersion `0x783880`

This handler:

1. unboxes/resolves one object/WAD from the Lua call argument;
2. locates that WAD in the global WAD array using stride `0xEE28`;
3. resolves the WAD's staged-record index;
4. reads the corresponding `0xA8` staged record;
5. returns only the two fixed 16-bit metadata fields at `record+0xA4` and `record+0xA6` (or zero/default values based on record flags).

It likewise does not expose Channel A, Channel B, arbitrary record bytes, or custom-userdata state.

### Save pipeline context

The static path remains proven:

```text
SaveGame 0x84F1C0
  -> 0x66B650
  -> 0x6687F0
  -> 0x82C820 / staged serialization
```

This is write-side integration evidence only and must not be invoked by Completionist Map.

### Conclusion

Close the short direct built-in Lua bridge route:

- VFS route: closed;
- `package.loadlib`: closed;
- `ResolveGameObject / GetRef* / LoadCheck`: closed;
- reverse registered-Lua path: only fixed metadata readers plus write-side `SaveGame`;
- no existing registered Lua handler found that exposes arbitrary staged Raven custom-userdata authority.

Do not continue guessing built-in Lua API names.

The 53-state authority model remains solved. The remaining problem is **delivery architecture**: expose the proven read-only staged authority to the existing Lua map mod without modifying saves/progression and without redistributing the unlicensed Script Loader fork.


## Clean-room native bridge load-path proof queued

The handoff was re-read after closing the short direct built-in Lua bridge route.

Architecture constraints now proven:

- the full 53-Raven authority model is solved;
- no existing registered Lua API exposes arbitrary staged Raven custom-userdata;
- `SaveGame` reaches the staged owner but is write-side and must not be used;
- `package.loadlib` is disabled;
- the upstream Script Loader exposes no plugin ABI and has no redistribution license;
- do not fork/redistribute that loader for public release.

Therefore the next release architecture to test is a **separate clean-room native bridge loaded under another DLL name that GoW itself already imports**, while leaving the existing unmodified `version.dll` Script Loader in place.

New tooling:

- `c464b6f049c94fae720c09aae3403a699d6545ed` - `tools/v0.10.5/inspect-gow-native-bridge-load-options.py`
- `c5269a7d25125f4217ed607ae8777b6634e5ba49` - `tools/v0.10.5/inspect-gow-native-bridge-load-options-and-push.ps1`

The inspector is static/read-only. It parses normal and delay-load imports from the exact supported `GoW.exe`, then checks/ranks common secondary proxy candidates:

```text
dxgi.dll
dinput8.dll
winmm.dll
xinput1_4.dll
xinput9_1_0.dll
dbghelp.dll
dsound.dll
winhttp.dll
wininet.dll
cryptsp.dll
```

`version.dll` is explicitly marked unavailable because Script Loader already occupies that proxy name.

The report includes:

- whether each candidate is actually imported;
- normal vs delay-load use;
- exact imported symbol names/ordinals;
- number of exports a forwarding proxy would need;
- the lowest-complexity imported candidate.

Acceptance decision:

- if a viable secondary proxy DLL exists, use it for a clean-room Completionist Map native bridge and keep the upstream Script Loader untouched;
- if no viable secondary proxy is imported, fall back to a separate launcher/injector architecture rather than modifying the upstream loader.

This step performs no process access, game launch, save access, progression write, or game-file write.


## Native bridge load-option result - dxgi.dll selected

Evidence commit:

- `8f8f126c97424d31db4619ff53f11211eab768fa`
- evidence: latest `archive/field-logs/source-scans/gow-native-bridge-load-options-*/`

Static import inspection completed safely:

```text
GOW_NATIVE_BRIDGE_LOAD_OPTIONS_COMPLETE
imported_dlls=38
preferred=dxgi.dll
save_opened=false
save_written=false
progression_written=false
game_launched=false
```

Relevant load candidates:

```text
dxgi.dll
  imported=true
  normal import
  imported symbols=1
  CreateDXGIFactory1

XINPUT1_4.dll
  imported=true
  normal import
  imported ordinals=2,3
  imported symbols=2

VERSION.dll
  imported=true
  imported symbols=2
  GetFileVersionInfoA
  VerQueryValueA
  unavailable for Completionist Map because upstream Script Loader already occupies version.dll
```

Decision:

- select `dxgi.dll` as the primary clean-room native bridge load point;
- keep `XINPUT1_4.dll` only as fallback;
- leave the existing upstream Script Loader `version.dll` untouched;
- do not redistribute a modified Script Loader.

The `dxgi.dll` proxy surface is minimal: GoW directly imports only `CreateDXGIFactory1`, so a clean-room bridge can forward that export to the real system DXGI and perform Completionist Map initialization independently.

Next step should be implementation-focused, not another broad research pass: build a minimal reversible development proof of a clean-room `dxgi.dll` bridge that forwards `CreateDXGIFactory1`, initializes safely outside loader-lock, proves it coexists with the existing Script Loader, and exposes **read-only** Raven authority without save/progression writes.

Use a long Codex/Sol pass for this implementation so the new usage window is spent on one coherent build/testable deliverable rather than multiple short speculative probes.


## Clean-room DXGI bridge implementation - proxy and native authority reader complete

Implementation stage commits begin at:

- `667b8fd` - clean-room x64 `dxgi.dll` proxy, System32-only `CreateDXGIFactory1` forwarding, safe post-forward worker start, offline forwarding tests, and reproducible MSVC/CMake build.

The next stage ports the already-accepted authority model into the DLL. It does not reopen Raven research. The bridge now uses:

- exact supported `GoW.exe` SHA-256 gate;
- the proven staged table/pool RVAs and `0xA8` record layout;
- two equal bounded in-process reads;
- cached Channel-A Lua length framing;
- bounded carrier/graph decode;
- the exact 53-entry `(registry_hash, object_hash)` catalogue;
- absent-WAD default-false only when the WAD is absent from the complete staged snapshot;
- an atomic native `CompletionistMapGetRavenSnapshotV1` API.

Fresh offline verification against the accepted 425-record capture reports:

```text
RAVEN_BRIDGE_AUTHORITY_TESTS_PASSED states=53 explicit=42 absentWadFalse=11 killed=27 alive=26
```

It also verifies Veithurgard `false,true,true` and concurrent all-or-nothing snapshot publication.

Current exact boundary:

- proxy/load path: implemented and offline-forwarding proven;
- native 53-state authority reader: implemented and accepted-capture proven;
- save/progression writes: none;
- upstream `version.dll`: untouched;
- remaining boundary: deliver the native snapshot to existing map/compass Lua without raw engine patching, or prove a native marker synchronization route.

Do not redo authority, identity, save codec, absence, VFS, `package.loadlib`, or built-in Lua API research. Finish fail-closed install/rollback and one runtime load-proof runner before user testing.


## DXGI bridge install and rollback gates complete

Fail-closed tools now exist:

- `tools/v0.10.5/build-raven-authority-bridge.ps1`
- `tools/v0.10.5/install-raven-authority-bridge.ps1`
- `tools/v0.10.5/rollback-raven-authority-bridge.ps1`
- `tools/v0.10.5/test-raven-authority-bridge-install.ps1`

The build emits an ignored artifact manifest with exact DLL hash and source commit. Install requires the supported exe hash, verifies `version.dll` before/after, and refuses unknown or changed `dxgi.dll`. Upgrade backs up the prior owned DLL and manifest. Rollback deletes only the exact manifest hash and can restore the prior owned pair.

Fresh temp-root result using a read-only copy of the supported game executable:

```text
RAVEN_NATIVE_BRIDGE_INSTALL_TESTS_PASSED clean=true upgrade=true unknown_refused=true tamper_refused=true version_untouched=true
```

No live game directory was changed by this test. Next task is one self-logging user runtime runner that installs, launches, captures load/snapshot proof, rolls back, archives evidence, commits, and pushes.


## RAVEN_NATIVE_BRIDGE_LOAD_PROOF_READY

The complete targeted runner is now:

`tools/v0.10.5/run-raven-authority-bridge-load-proof-and-push.ps1`

It:

1. rebuilds and runs all three offline test executables;
2. installs only the manifest-owned `dxgi.dll` after exact exe/hash gates;
3. launches GoW and asks for one advanced-save plus map-open pass;
4. requires fresh log proof for System32 proxy load, successful `CreateDXGIFactory1` forwarding, supported exe acceptance, and `count=53 unknown=0` atomic authority;
5. rolls back to the exact pre-run `dxgi.dll`/manifest state;
6. verifies `version.dll` is byte-identical;
7. archives, commits, and pushes the evidence.

Exact user command from repository root, with GoW closed:

```powershell
git pull --ff-only origin codex/all-ravens-release-candidate; & .\tools\v0.10.5\run-raven-authority-bridge-load-proof-and-push.ps1
```

No more static authority research is needed. The one open boundary after load proof is native-snapshot delivery into the existing Lua map/compass implementation. Do not claim `RAVEN_NATIVE_BRIDGE_RUNTIME_READY` until that delivery is implemented and the fresh/advanced/immediate-kill/map-reopen fixtures pass end to end.


## Codex Sol DXGI bridge implementation task prepared

A long implementation-focused Codex/Sol task has been added:

- `d7051fc749d32c61809d8dea3dc65a1f9f6096eb`
- `docs/research/CODEX-SOL-v0105-raven-dxgi-native-bridge-task.md`

Purpose:

- spend the next fresh Codex usage window on one coherent buildable deliverable rather than another short exploratory pass;
- implement the selected clean-room `dxgi.dll` proxy architecture;
- preserve the untouched upstream `version.dll` Script Loader;
- port/reuse the already-accepted 53-state Raven authority;
- solve delivery either through legitimate in-process Lua API registration or, if that cannot be done safely, native marker synchronization;
- build fail-closed install/rollback tooling;
- push every meaningful stage;
- stop only with a buildable development proof or one exact runtime blocker plus its complete runner.

Primary success target:

`RAVEN_NATIVE_BRIDGE_RUNTIME_READY`

Acceptable intermediate target:

`RAVEN_NATIVE_BRIDGE_LOAD_PROOF_READY`

Do not spend that window redoing closed Lua/VFS/save-codec/identity research.


## Load-proof runner verified before live test

Assistant verification against branch HEAD:

- HEAD: `ccd310013a4d18790ac6bca1792f9a4396bd286e`
- branch: `codex/all-ravens-release-candidate`
- runner: `tools/v0.10.5/run-raven-authority-bridge-load-proof-and-push.ps1`

Verified success gates in the runner:

```text
RAVEN_NATIVE_BRIDGE_PROXY_LOADED
RAVEN_NATIVE_BRIDGE_DXGI_FORWARDED ... success=true
RAVEN_NATIVE_BRIDGE_EXE_ACCEPTED
RAVEN_NATIVE_BRIDGE_SNAPSHOT_ACCEPTED ... count=53 unknown=0
RAVEN_NATIVE_BRIDGE_DELIVERY_PENDING
```

The runner also:

- requires GoW closed before install;
- rebuilds and reruns native tests;
- installs only the manifest-owned `dxgi.dll`;
- records the pre-test `version.dll` hash;
- launches GoW for one advanced-save/map-open pass;
- extracts only fresh bridge-log lines;
- rolls the bridge back;
- verifies exact pre-run `dxgi.dll`/manifest restoration;
- verifies `version.dll` remains byte-identical;
- archives the result and pushes it to the same branch;
- attempts rollback even on failure.

Next action is the live load proof. No additional static research or implementation should be done before this result.

After the proof is pushed, inspect the new runtime-capture evidence first. If it passes, the only remaining architecture boundary is delivery of the accepted native snapshot into the existing Lua map/compass implementation.


## Live load-proof attempt blocked by PowerShell execution policy

The first live-test command did **not** enter the runner.

Observed local error:

```text
PSSecurityException
running scripts is disabled on this system
FullyQualifiedErrorId : UnauthorizedAccess
```

The failure occurred at direct invocation of:

`tools/v0.10.5/run-raven-authority-bridge-load-proof-and-push.ps1`

Therefore:

- the proof runner itself did not start;
- no bridge build/install step from that runner executed;
- GoW was not launched by the runner;
- no `dxgi.dll` install/rollback action from the runner occurred;
- no save/progression/game-file mutation from this attempt occurred.

Next action: run the same proof through a child PowerShell process with `-NoProfile -ExecutionPolicy Bypass -File`. This changes execution policy only for that one PowerShell process and does not modify the machine-wide policy.


## Runtime load proof: minimal DXGI proxy design FAILED

Runtime evidence commit:

- `1fd7d61b8bdf71189b6e60a1fbd8e59e8c71ae95`
- capture: `archive/field-logs/runtime-captures/raven-native-bridge-load-proof-20260921-102726/`

Observed startup failure:

```text
GoW.exe - Entry Point Not Found

The procedure entry point CreateDXGIFactory2 could not be located
in the dynamic link library C:\WINDOWS\SYSTEM32\d3d11.dll.
```

The proxy source at the failing commit exports only:

```text
CreateDXGIFactory1
CompletionistMapGetRavenSnapshotV1
```

Root cause:

- static inspection of `GoW.exe` showed only one direct DXGI import, `CreateDXGIFactory1`;
- that was insufficient as a proxy compatibility model;
- once local `dxgi.dll` is loaded for the process, dependent system modules such as `d3d11.dll` also resolve their DXGI imports against that local module;
- `d3d11.dll` requires `CreateDXGIFactory2` on this Windows build;
- the minimal Completionist Map proxy does not export it, so loader resolution fails before normal game startup/bridge authority proof.

Therefore the **single-export DXGI proxy design is closed**. Do not retry this binary.

The failed proof runner itself later recorded:

```text
rollback_exact=true
version_dll_untouched=true
bridge_save_writes=false
bridge_progression_writes=false
```

and:

```text
RAVEN_NATIVE_BRIDGE_ROLLED_BACK
restored_previous=false
version_untouched=true
```

The unrelated runner-side `Count` PowerShell exception occurred after the failed game-launch attempt and is a second bug to fix before the next proof.

Immediate priority:

1. verify/remove only any recognized Completionist Map `dxgi.dll` residue from the live game root;
2. get vanilla+existing Script Loader GoW launching again;
3. do not install another DXGI bridge until a compatibility-complete forwarding surface is implemented and tested.

Next implementation options to evaluate with Codex/Sol:

- robust DXGI proxy with compatibility-complete forwarding for the real System32 DXGI export surface used by GoW + system graphics modules/overlays, while intercepting only the needed initialization point; or
- switch to the `XINPUT1_4.dll` fallback and forward the complete XInput surface/ordinals, if that yields a substantially smaller and safer proxy contract.

Do not modify `version.dll`, saves, or progression.


## Fail-closed startup recovery prepared

Recovery tool:

- `14582de94a8da894969fcfaf457160ccc3680c3e`
- `tools/v0.10.5/recover-raven-authority-bridge-startup.ps1`

It is intentionally narrow:

- requires GoW closed;
- recognizes the failed bridge by exact SHA-256
  `2e93c9c711a5c0f622a4b977b4c8f3e4bc81f0e5b1a8640eb2946830d3d2bd2a`
  or by the owned Completionist Map manifest;
- refuses to delete an unknown game-root `dxgi.dll`;
- removes only the owned/stale Raven native bridge manifest;
- removes only matching Completionist Map temporary DXGI copies;
- verifies `version.dll` stays byte-identical during recovery;
- refuses launch if any game-root `dxgi.dll` or Raven bridge manifest still remains;
- optionally launches GoW after successful cleanup.

Use this before any further native-bridge development or runtime test.


## Startup recovery confirmed successful

User ran the fail-closed recovery tool and reported a successful normal GoW launch afterward.

This confirms:

- the failed Completionist Map DXGI bridge was the startup blocker;
- removing that bridge restored normal startup;
- the existing upstream `version.dll` Script Loader installation remains usable;
- no further live native-bridge test should occur until the proxy compatibility contract is fixed.

Do not reinstall the single-export DXGI bridge.

Next implementation pass must:

1. fix proxy compatibility before live install;
2. fix the runner's PowerShell scalar/`.Count` bug;
3. add offline/load-contract tests that would have caught the missing `CreateDXGIFactory2` export before installation;
4. compare a compatibility-complete DXGI proxy against the `XINPUT1_4.dll` fallback and choose the smaller/safer complete proxy surface;
5. only then prepare another reversible live proof.


## Codex Sol proxy compatibility hardening task prepared

New focused task:

- `c548f949812966950d67da1ebcd502cbeb03e868`
- `docs/research/CODEX-SOL-v0105-native-bridge-proxy-compatibility-task.md`

This task starts from the recovered healthy game state and explicitly forbids reinstalling the single-export DXGI proxy.

It requires Sol to:

- compare compatibility-complete DXGI vs compatibility-complete `XINPUT1_4.dll`;
- choose the lower-risk complete proxy surface;
- preserve the accepted 53-Raven native authority reader;
- add an export-contract test that would have rejected the missing `CreateDXGIFactory2` proxy;
- fix the runtime proof runner's scalar/`.Count` bug;
- add startup-failure/rollback regression tests;
- update install/rollback/recovery if the proxy DLL name changes;
- push only when `RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V2_READY`.

No further live bridge install should occur before those offline gates pass.


## Proxy compatibility hardening complete - V2 load proof ready

Implementation commits:

- `ca7402a` - replace the closed minimal DXGI design with a compatibility-complete `XINPUT1_4.dll` proxy;
- `3ccab7a` - migrate manifest ownership, install, rollback, and recovery to schema-2 XInput handling;
- `388a913` - fix the proof runner scalar bug and add startup/failure/rollback regression coverage.

Architecture decision:

- real System32 `dxgi.dll`: 20 named exports and high process-wide graphics/overlay conflict risk;
- real System32 `XINPUT1_4.dll`: 15 exports total, 8 named and 7 ordinal-only;
- selected `XINPUT1_4.dll` as the smaller, lower-risk complete proxy surface.

The proxy contract is generated from:

`native/raven-authority-bridge/xinput1_4-export-contract.json`

It preserves exact ordinals:

```text
1,2,3,4,5,7,8,10,100,101,102,103,104,108,109
```

Generated x64 tail thunks preserve Win64 argument registers, resolve the absolute System32 DLL outside `DllMain`, and tail-jump without changing XInput semantics. The Raven snapshot API remains exported separately at ordinal 110. The accepted authority decoder was not redesigned.

Fresh offline gates:

```text
RAVEN_BRIDGE_EXPORT_CONTRACT_TEST_PASSED system_exports=15 named=8 ordinal_only=7
RAVEN_BRIDGE_FORWARDING_TEST_PASSED target=XINPUT1_4.dll
RAVEN_BRIDGE_AUTHORITY_TESTS_PASSED states=53 explicit=42 absentWadFalse=11 killed=27 alive=26
100% tests passed, 0 tests failed out of 4
RAVEN_NATIVE_BRIDGE_INSTALL_TESTS_PASSED target=XINPUT1_4.dll clean=true upgrade=true unknown_refused=true tamper_refused=true recovery=true version_untouched=true
RAVEN_NATIVE_BRIDGE_RUNNER_TESTS_PASSED zero=true one=true multiple=true early_exit=true missing_log=true script_loader=true rollback=true
```

The proof runner now:

- uses arrays safely for zero, one, or many log lines;
- treats early GoW exit or absent fresh proxy log as load failure;
- requires fresh Script Loader evidence from the Completionist Map API line;
- stops a launched game on failure before rollback;
- restores the exact prior `XINPUT1_4.dll` and manifest state;
- verifies `version.dll` byte-identical;
- archives and pushes both pass and failure evidence.

## RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V2_READY

Run exactly one command from repository root with GoW closed:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\tools\v0.10.5\run-raven-authority-bridge-load-proof-and-push.ps1
```

Do not reinstall the old `dxgi.dll` proxy. Do not attempt Lua/map delivery until this V2 load proof passes. The remaining post-proof boundary is still delivery of the accepted native 53-state snapshot into the existing map/compass runtime.


## V2 XInput load-proof runner verified before live test

Assistant verification against branch HEAD:

- HEAD: `57c1369e56be54e00edfdbe4d33497a0289db7cc`
- proxy target: `XINPUT1_4.dll`
- old game-root `dxgi.dll` proxy path is no longer used.

Verified XInput contract source:

`native/raven-authority-bridge/xinput1_4-export-contract.json`

It defines the complete 15-export target contract and preserves exact ordinals:

```text
1,2,3,4,5,7,8,10,100,101,102,103,104,108,109
```

The proxy runtime resolves the real System32 `XINPUT1_4.dll`, validates named exports against the same ordinal address, and forwards through generated tail thunks. The Raven snapshot API is separate at ordinal 110.

Verified V2 runner:

`tools/v0.10.5/run-raven-authority-bridge-load-proof-and-push.ps1`

It now:

- requires GoW closed;
- runs runner regression tests first;
- rebuilds the bridge and native tests;
- runs installer ownership/recovery tests;
- installs only owned `XINPUT1_4.dll`;
- waits for a fresh proxy startup observation while the launched GoW process remains alive before prompting the user;
- treats early GoW exit or missing fresh startup log as immediate load failure;
- captures fresh bridge and Script Loader logs;
- requires:
  - proxy loaded;
  - XInput forwarding ready;
  - supported exe accepted;
  - Raven snapshot `count=53 unknown=0`;
  - delivery-pending marker;
  - Completionist Map loaded through the existing Script Loader;
- uses arrays for zero/one/multiple log matches, closing the prior scalar `.Count` bug;
- on failure stops the launched GoW process before rollback;
- restores exact pre-run `XINPUT1_4.dll` and manifest state;
- verifies `version.dll` remains byte-identical;
- archives and pushes both pass and failure evidence.

Installer and rollback are schema-2/XInput-specific and refuse unknown existing `XINPUT1_4.dll` ownership.

Next action is the V2 live load proof. Do not implement Lua/map delivery until the pushed V2 proof is inspected and passes.


## V2 live proof failed at Steam bootstrap handoff

Runtime evidence commit:

- `93834dd91dcab4799f66a017e8d23c856ab502af`
- capture: `archive/field-logs/runtime-captures/raven-native-bridge-load-proof-v2-20260921-110832/`

Runner result:

```text
RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V2_FAILED
reason=Game exited before bridge startup proof. exit_code=53
rollback_exact=true
version_dll_untouched=true
bridge_save_writes=false
bridge_progression_writes=false
```

No fresh bridge or Script Loader log was captured:

```text
NO_FRESH_BRIDGE_LOG_LINES
NO_FRESH_LOADER_LOG_LINES
```

However the user separately observed that GoW **did launch successfully** after the runner started it.

Interpretation:

- the process returned by `Start-Process GoW.exe -PassThru` is not necessarily the final long-lived game process;
- on this Steam installation it can exit during Steam restart/handoff while Steam launches a successor GoW process;
- the V2 runner incorrectly treats that bootstrap exit as definitive startup failure and rolls the XInput proxy back too early;
- therefore this proof says nothing negative yet about the XInput proxy runtime itself.

The XInput proxy and ownership gates remain valid. The open blocker is runner process tracking.

Next runner must:

1. allow the initially launched process to exit during a Steam handoff;
2. keep the owned `XINPUT1_4.dll` installed while waiting for a successor `GoW/GodOfWar` process;
3. require fresh bridge startup evidence and a live successor process before prompting;
4. only declare failure if no live successor process plus fresh proxy log appears within the startup timeout;
5. on failure terminate any GoW successor processes created during the proof before rollback;
6. preserve exact rollback and `version.dll` checks.

Do not change Raven authority or proxy forwarding while fixing this runner behavior.


## Steam-aware V2 runner patch ready

The V2 proof itself did not disprove the XInput bridge. It exposed a runner assumption: the PID returned by direct `GoW.exe` launch can exit during Steam handoff while a successor game process launches successfully.

Fix commits:

- `cfc8712397203263bf896c6f46ecf1516349a150` - startup observation now requires both a fresh proxy log and a live game process, but treats process absence as a wait state rather than immediate failure;
- `19f035270c548eebfce718d657b95069358d6238` - regression coverage for Steam handoff gap, proxy-log-before-successor, live-process+log success, missing log, Script Loader evidence, and rollback;
- `65ff0d60d8f518ceff52e85da99bfc5150585d58` - live runner now tracks any successor `GoW/GodOfWar` PID instead of only the bootstrap PID.

New startup behavior:

1. snapshot baseline GoW PIDs (normally none because the runner requires GoW closed);
2. launch `GoW.exe`;
3. tolerate the returned bootstrap process exiting, including the previously observed exit code 53;
4. keep the owned `XINPUT1_4.dll` installed during the handoff window;
5. poll for any new live `GoW/GodOfWar` successor process;
6. require both:
   - fresh `RAVEN_NATIVE_BRIDGE_PROXY_LOADED` evidence;
   - at least one live successor game process;
7. only fail after the full startup timeout if that combined condition never appears.

The runner also archives `startup-processes.txt` with bootstrap PID/exit code and the live successor PID(s).

No Raven authority, XInput forwarding, install, rollback, save, or progression behavior changed.

Next action: rerun the same V2 proof with GoW closed. If it passes, the proxy/load layer is proven and the next boundary is native snapshot delivery to the map/compass runtime.


## Steam-aware V2 retry: game runs but XInput proxy emits no bridge log

Runtime evidence commit:

- `2fcbb1bb38277049ee81d803842fe62c092fcde9`
- capture: `archive/field-logs/runtime-captures/raven-native-bridge-load-proof-v2-20260921-111655/`

Observed result:

```text
result=RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V2_FAILED
reason=Expected fresh bridge startup log plus a live GoW process did not appear within 30 seconds. bootstrap_exit_code=53
rollback_exact=false
version_dll_untouched=true
```

Important evidence:

- the initial direct `GoW.exe` process again exited with code 53;
- fresh Script Loader log contains hundreds of normal game startup/script-load lines beginning at 14:17:22;
- therefore the actual game process did run;
- `bridge-log-fresh.txt` contains only `NO_FRESH_BRIDGE_LOG_LINES`;
- there was no `RAVEN_NATIVE_BRIDGE_PROXY_LOADED` line at all;
- the runner timed out rather than reaching its user prompt.

This means the current blocker is **not** Steam PID tracking anymore. The actual game launched, but the game-root `XINPUT1_4.dll` did not produce evidence that it was loaded/initialized.

The proof does not yet distinguish between:

1. the successor game process never loading the game-root XInput proxy at all;
2. Windows loader KnownDLL/API-set behavior resolving XInput from System32 despite the local file;
3. the proxy module loading but none of its forwarded exports being called, with logging tied too late to first export resolution.

The next observation must identify the actual loaded XInput module path in the live GoW process. Do not speculate between these possibilities.

Rollback note:

- `rollback-error.txt` says `Close God of War first.`;
- automatic rollback failed while the real game process was still alive;
- `rollback_exact=false`;
- `version.dll` remained untouched;
- pre-run state had no game-root `XINPUT1_4.dll` and no bridge manifest.

Immediate priority: with GoW fully closed, run the schema-2 recovery tool to remove/rollback only the owned Completionist Map XInput proxy and manifest. Verify the game root is clean before any further bridge test.

After cleanup, build a **read-only live module-path observer** that records which `XINPUT1_4.dll` module the actual long-lived GoW process loaded, if any, before choosing the next architecture. Do not modify Raven authority, saves, progression, or `version.dll`.
