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


## Read-only live XInput module-path observer queued

New tooling:

- `7ca8ef76f6af85a0885e809125517f10dcfebad4`
- `tools/v0.10.5/capture-gow-loaded-module-paths-readonly-and-push.ps1`

Purpose:

- answer the current runtime question directly without installing any native proxy;
- launch GoW from a clean recovered game root;
- tolerate the Steam bootstrap/handoff;
- find the actual readable long-lived `GoW/GodOfWar` process;
- enumerate its loaded module paths read-only;
- report specifically:
  - `XINPUT1_4.dll`
  - `version.dll`
  - `dxgi.dll`
  - full module list for context;
- archive and push the evidence.

Safety gates:

- refuses to run if GoW is already open;
- refuses to run if a game-root `XINPUT1_4.dll` exists;
- refuses to run if the Raven native bridge manifest still exists;
- performs no process writes;
- performs no save/progression writes;
- installs no proxy;
- writes only repository evidence.

The capture waits briefly for modules to settle, then asks the user to quit GoW before it commits/pushes the evidence.

Acceptance:

- if `XINPUT1_4.dll` is loaded from System32, the local-proxy architecture is being bypassed by loader behavior and should be abandoned;
- if no `XINPUT1_4.dll` is loaded at all, XInput is not a viable automatic load point for this game path;
- if a game-root XInput path appears only when a proxy is installed, then revisit initialization timing/logging rather than load-point selection.

Do not change Raven authority while resolving this.


## Module-path observer enumeration bug fixed

Failed capture evidence:

- `fd3959ffeb8cf11d962c54973c1959068cf39fe2`
- capture: `archive/field-logs/runtime-captures/gow-loaded-module-paths-20260921-112406/`

The observer successfully found the actual long-lived game process:

```text
Live GoW process found: PID=2980
```

but failed after the 10-second settle period with:

```text
Module enumeration failed for PID 2980:
The property 'ModuleName' cannot be found on this object.
```

Root cause is in the observer tooling, not GoW or module access:

- `@($Process.Modules)` was treated as one `ProcessModuleCollection` object by this PowerShell/.NET runtime;
- the loop variable therefore became the collection instead of an individual `ProcessModule`;
- `ModuleName` does not exist on the collection.

Fix commit:

- `6b0583a6ae67ab9872288a1c033a476be92fe41a`

The observer now:

1. stores `$Process.Modules` as `$moduleCollection`;
2. iterates from `0` to `$moduleCollection.Count - 1`;
3. accesses each module by index;
4. reads `ModuleName/FileName/BaseAddress/ModuleMemorySize` from the actual `ProcessModule`.

No native proxy, process writes, save writes, progression writes, or game-file writes are introduced by this fix.

Next action: rerun the same read-only module-path capture with GoW fully closed. The result should directly settle whether the live game process loads `XINPUT1_4.dll` from System32, the game directory, or not at all.


## Module-path observer Count bug fixed

Second failed capture evidence:

- `08016f53b90bc5cf6fbf6edb1973f7d35087fb3c`
- capture: `archive/field-logs/runtime-captures/gow-loaded-module-paths-20260921-112801/`

The observer again successfully found the long-lived GoW process:

```text
Live GoW process found: PID=29972
```

but then failed with:

```text
Module enumeration failed for PID 29972:
The property 'Count' cannot be found on this object.
```

This confirms the same PowerShell/.NET collection-wrapper issue one level later: the `Process.Modules` object is available, but direct `.Count` access is not reliable in this runtime.

Fix commit:

- `335e47554a743c99524d35b4e1e21e387afa3ba0`

The observer now avoids PowerShell collection semantics entirely:

1. casts the module collection to `System.Collections.IEnumerable`;
2. obtains its explicit .NET enumerator;
3. walks modules with `MoveNext()`;
4. casts each item to `System.Diagnostics.ProcessModule`;
5. reads `ModuleName`, `FileName`, `BaseAddress`, and `ModuleMemorySize`;
6. disposes the enumerator if applicable.

This remains fully read-only and does not install a proxy or modify process memory, saves, progression, `version.dll`, or game files.

Next action: rerun the same module-path capture with GoW fully closed.


## Module observer switched to Toolhelp snapshot

Third failed capture evidence:

- `25ee58559baacb72bb91053b652a121fb8e2bc5b`
- capture: `archive/field-logs/runtime-captures/gow-loaded-module-paths-20260921-113426/`

The observer again found the real long-lived GoW process:

```text
Live GoW process found: PID=51064
```

but `Process.Modules` failed again, this time with:

```text
Module enumeration failed for PID 51064:
You cannot call a method on a null-valued expression.
```

The user also reported that GoW takes roughly **35 seconds to reach the main menu** on this machine. The previous observer waited only 10 seconds after detecting the long-lived process.

Conclusion:

- stop using PowerShell/.NET `Process.Modules` entirely for this evidence path;
- do not treat a 10-second post-process delay as a settled module set on this machine.

Fix commit:

- `04aafe9fd79f3878972b391d42e2fe7784c517f5`

The observer now:

1. uses Windows Toolhelp APIs directly:
   - `CreateToolhelp32Snapshot`
   - `Module32FirstW`
   - `Module32NextW`
2. requests only module enumeration flags (`TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32`);
3. performs no process writes or memory modification;
4. no longer touches `Process.Modules`;
5. changes the default module-settle delay from 10 seconds to **40 seconds**, slightly beyond the user's observed ~35-second main-menu time;
6. still refuses any installed game-root XInput proxy/bridge manifest before capture.

The next run should therefore capture the stable long-lived GoW module list without relying on PowerShell's ProcessModuleCollection behavior.

Next action: rerun the same read-only module-path observer with GoW fully closed.


## Module observer switched from Toolhelp to PSAPI

Fourth failed capture evidence:

- `bc527c9eea67342ab1891fecdf7cdc063197cdc4`
- capture: `archive/field-logs/runtime-captures/gow-loaded-module-paths-20260921-113723/`

The observer again found the long-lived GoW process and waited the updated 40-second settle interval:

```text
Live GoW process found: PID=51916
Waiting 40 seconds for modules to settle...
```

Then Windows Toolhelp module enumeration failed:

```text
CreateToolhelp32Snapshot failed.
```

The archived exception did not expose a useful Win32 code through the PowerShell wrapper. Since three separate `Process.Modules` approaches and now Toolhelp have failed, stop iterating on those APIs.

Important user timing note:

- GoW takes roughly 35 seconds to reach the main menu on this machine;
- the observer now waits 40 seconds, so process/module-settle timing is no longer the likely blocker.

Also, loading a save is **not required** for the XInput load-point question because static evidence already shows `XINPUT1_4.dll` as a normal GoW import; it should be resolved during process startup.

Fix commit:

- `df21d3db3c13c27fde41cb5442ae7d81a6a69e04`

The observer now uses the read-only PSAPI route:

1. `OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ)`;
2. `EnumProcessModulesEx(..., LIST_MODULES_ALL)`;
3. `GetModuleFileNameExW` for the exact module path;
4. `GetModuleInformation` for base address and image size;
5. closes the process handle.

No process writes, memory modification, save/progression writes, proxy install, or game-file modification are performed.

If PSAPI succeeds, the result should finally settle whether the live process uses System32 `XINPUT1_4.dll`, a game-root copy, or no XInput module at all.

Do not spend remaining Codex/Sol usage on this capture plumbing. Preserve it for the next substantive bridge/delivery implementation step once the load-point evidence is known.


## Full module enumeration abandoned after ERROR_PARTIAL_COPY

Fifth failed module-list capture:

- `11c7b68175f0a390c7af5d5deaa622e829411546`
- capture: `archive/field-logs/runtime-captures/gow-loaded-module-paths-20260921-114210/`

The observer found the live GoW process and waited the full 40-second settle window:

```text
Live GoW process found: PID=41928
Waiting 40 seconds for modules to settle...
```

PSAPI then failed with:

```text
EnumProcessModulesEx failed (error 299)
```

Win32 error 299 is `ERROR_PARTIAL_COPY`.

At this point the following broad module enumeration routes have all been exhausted on this machine:

- PowerShell/.NET `Process.Modules` direct enumeration;
- indexed `ProcessModuleCollection`;
- explicit `IEnumerable` enumerator;
- Toolhelp `CreateToolhelp32Snapshot(TH32CS_SNAPMODULE*)`;
- PSAPI `EnumProcessModulesEx`.

Do not spend more time trying to enumerate GoW's entire module list.

The actual research question is much smaller: which mapped image owns GoW's already-resolved `XINPUT1_4.dll` import slots?

## Targeted XInput IAT owner probe CI-proven and ready

New native probe:

- `2bd18553e575d4acb3fa157fad632fc0ec168d27`
- `native/raven-authority-bridge/tools/live_import_probe.cpp`
CMake target:

- `d551431cdc512f2ae5265e717b1240a33460cda9`
- `raven_bridge_import_probe`

Warning-gate cleanup:
- `d85da4bb6d95b5b5fa20e0ee90518753d088fb67`

New fail-soft live runner:

- `fb7610a7ff5c8bdde7231215cb05042b25774f73`
- `tools/v0.10.5/capture-gow-xinput-iat-owner-readonly-and-push.ps1`

The native probe intentionally does **not** enumerate the process module list.

It:

1. parses the normal PE import directory in the on-disk supported `GoW.exe`;
2. finds the `XINPUT1_4.dll` import descriptor and exact IAT slots;
3. opens the live process read-only with `PROCESS_QUERY_INFORMATION | PROCESS_VM_READ`;
4. obtains the remote PEB with `NtQueryInformationProcess(ProcessBasicInformation)`;
5. reads the remote image base and only the exact XInput IAT slot pointers via `ReadProcessMemory`;
6. identifies the mapped image containing each resolved target by walking the PEB loader list read-only;
7. falls back to `GetMappedFileNameW` for the individual target address if needed;
8. prints the exact owner path/method for each imported XInput slot.

This is targeted and reuses the `ReadProcessMemory` capability already proven reliable throughout Raven research.

### Remote Windows compile/self-test gate

A temporary branch-only GitHub Actions workflow was added solely to compile and self-test the native probe on a clean Windows x64 runner.

Initial CI failure was infrastructure-only:

- GitHub `windows-latest` had moved to a Visual Studio 2026 image;
- the first temporary workflow requested the absent `Visual Studio 17 2022` generator.

The workflow was corrected to `Visual Studio 18 2026`.

The probe then:

- configured successfully;
- compiled successfully under MSVC with `/W4 /WX /permissive- /EHsc`;
- ran its live PEB-reader self-test successfully:

```text
RAVEN_IMPORT_PROBE_SELFTEST_PASSED owner=C:\Windows\System32\KERNEL32.DLL
```

The newest warning-clean commit CI run also completed with:

```text
status=completed
conclusion=success
```

CI run:

- `35596557736`

The temporary workflow was removed after validation:

- `d4e1e91e21e45a36b11082764080d989a0cff860`

Therefore the user is **not** being used as the compile test for this probe.

### Fail-soft live runner behavior

`capture-gow-xinput-iat-owner-readonly-and-push.ps1`:

- requires GoW closed initially;
- refuses any installed game-root `XINPUT1_4.dll` or Raven native bridge manifest;
- performs a clean native build and runs all existing native tests;
- runs the CI-proven probe `--self-test` before launching GoW;
- launches GoW and tolerates the Steam bootstrap/handoff;
- finds the long-lived GoW process by PID;
- waits 40 seconds, matching the user's observed ~35-second main-menu startup time;
- **does not require loading a save**;
- runs the targeted XInput IAT-owner probe;
- also records fail-soft secondary evidence from:
  - KnownDLL registry state;
  - `tasklist /m XINPUT1_4.dll`;
- archives and pushes the evidence automatically;
- does not require the user to press Enter;
- deliberately leaves GoW running after capture;
- does not install any native proxy;
- performs no process writes;
- performs no save/progression writes;
- performs no game-file writes.

If the targeted live probe itself cannot fully resolve the owner, the runner records `CAPTURE_INCOMPLETE` and still pushes all evidence rather than dying on a secondary observation method.

Next action: run this targeted capture once with GoW closed. Leave the game at the main menu. No save load is needed.


## XINPUT1_4 local-proxy route CLOSED by targeted live IAT proof

Successful runtime evidence:

- commit: `1a6507bd4fd1a5c64e9d31b91b4add0dfafbd97f`
- capture: `archive/field-logs/runtime-captures/gow-xinput-iat-owner-20260921-115740/`

The CI-proven targeted native probe ran successfully against the actual long-lived GoW process after the 40-second main-menu settle window.

Exact live result:

```text
RAVEN_IMPORT_PROBE_PROCESS pid=4364 dll=XINPUT1_4.dll slots=2 image_base=0x7FF6189C0000
RAVEN_IMPORT_SLOT iat_rva=0xD48A48 ordinal=3 target=0x7FF87C0E9FA0 owner_method=peb owner=C:\WINDOWS\SYSTEM32\XINPUT1_4.dll
RAVEN_IMPORT_SLOT iat_rva=0xD48A50 ordinal=2 target=0x7FF87C0E9A60 owner_method=peb owner=C:\WINDOWS\SYSTEM32\XINPUT1_4.dll
RAVEN_IMPORT_PROBE_COMPLETE dll=XINPUT1_4.dll slots=2 owner_consistent=true
```

Runner result:

```text
result=GOW_XINPUT_IAT_OWNER_CAPTURE_COMPLETE
probe_exit_code=0
probe_complete=true
proxy_installed=false
process_writes=false
save_writes=false
progression_writes=false
game_file_writes=false
```

Secondary evidence:

```text
tasklist /m XINPUT1_4.dll:
GoW.exe 4364 XINPUT1_4.dll
```

KnownDLL registry evidence did not list `XINPUT1_4.dll` under the queried KnownDLLs key, but that does not change the actual live import ownership result.

This closes the XInput question:

- GoW's two normal XInput import slots are resolved to the System32 `XINPUT1_4.dll`;
- the previously installed game-root Completionist Map `XINPUT1_4.dll` produced no bridge startup line while GoW/Script Loader still ran normally;
- therefore the local `XINPUT1_4.dll` proxy is not a viable automatic bridge load point on this machine/runtime path.

**Do not spend further time on XInput proxy loading.**

The useful result is that this removes the last ambiguity from the V2 failure.

## Native load architecture next boundary

Return to DXGI as the only currently proven game-root automatic native load point:

- the earlier local `dxgi.dll` definitely reached Windows loader resolution;
- its failure was specifically an incomplete proxy export surface (`CreateDXGIFactory2` missing);
- therefore the next native-load implementation should be a compatibility-complete DXGI proxy, not another XInput experiment.

Requirements before next live DXGI test:

1. reconstruct/implement a complete transparent DXGI forwarding surface for the target Windows system `dxgi.dll`;
2. do not use the old single-export proxy;
3. add an export-contract gate that compares the built proxy against the real/system DXGI public export contract;
4. include at minimum all standard factory/debug/declaration exports required by system graphics modules and common consumers, not only GoW's direct imports;
5. preserve all ordinals where applicable;
6. intercept only one safe initialization path for Completionist Map startup;
7. preserve existing accepted Raven authority decoder/snapshot code unchanged;
8. keep `version.dll` untouched;
9. keep installer/rollback ownership fail-closed;
10. only prepare another live DXGI proof after offline load/resolve tests pass.

The post-load boundary remains delivery of the accepted atomic 53-state Raven snapshot into the existing map/compass runtime.

Do not redo Raven authority research.


## Complete DXGI proxy Sol task prepared

Focused next-pass task:

- commit: `406e5484667da4882f6204fddc8f9f5416ec934f`
- file: `docs/research/CODEX-SOL-v0105-dxgi-complete-proxy-task.md`

This task starts from the successful XInput IAT owner proof and explicitly forbids revisiting XInput or Raven authority research.

It directs Sol to:

- implement a compatibility-complete game-root `dxgi.dll` proxy;
- generate and validate the full real DXGI export contract, including names/ordinals;
- ensure `CreateDXGIFactory2` and the rest of the required public surface are present;
- use generated ABI-transparent forwarding rather than a hand-written partial proxy;
- preserve accepted Raven authority code;
- restore installer/rollback/recovery ownership to DXGI;
- add offline export-parity and load/resolve tests;
- use a Windows CI compile/test gate before involving the user;
- prepare a reversible V3 live proof only after all offline gates pass.

Target stop state:

`RAVEN_DXGI_COMPLETE_PROXY_LOAD_PROOF_READY`

Do not enter Lua/map delivery before a later live DXGI load proof actually passes.


## Complete DXGI proxy implementation advanced after Codex usage cutoff

The focused Sol pass reached the usage limit after pushing its native stage.

### Sol-pushed native stage

Commit:

- `e3afcad02f359f5c0f41c66ab6937ec525478708`
- message: `feat(v0.10.5): implement complete DXGI bridge proxy`

Sol reported and the remote commit confirms:

- target switched back to `dxgi.dll`;
- complete target System32 DXGI contract pinned:
  - 20 named exports;
  - ordinals 1-20;
  - `CreateDXGIFactory2` ordinal 12;
  - target System32 SHA-256:
    `b12aebf0f077d6c1394b50e2eecdd5e16072c9a0c871f30887b5d170cbf2eaae`;
- generated `.def`, MASM thunks, and contract header;
- full name/ordinal parity test;
- explicit incomplete-DXGI fixture rejection;
- temp-directory load/resolve test;
- safe calls through:
  - `CreateDXGIFactory`;
  - `CreateDXGIFactory1`;
  - `CreateDXGIFactory2`;
- explicit System32 real-DXGI load/no-recursion proof;
- accepted Raven authority code preserved.

Sol locally reported five native tests green before push.

After `e3afcad`, Sol began editing installer/rollback/recovery locally but hit the usage limit before committing those changes. Those uncommitted local edits are **not** source of truth and have now been superseded by the remote implementation below.

### Schema-3 DXGI ownership completed remotely

Production ownership was migrated from the closed XInput route to DXGI:

- `51c6a3203ece432b4fcaf8636f1eda15e4791aeb` - installer schema-3 DXGI ownership;
- `844833e4be19bd0ba6464be95355e9a53d86184d` - staged DXGI rollback;
- `d9d707ba4ca590e4eb0c3be57157c51a5e33ef32` - DXGI-only recovery;
- `ed9a732f50c05fbaa2b367914cba89b6e8f3a9d1` - temp-root install/upgrade/rollback/recovery tests.

Production target:

```text
dxgi.dll
schema=3
proxy_contract=system32-dxgi-v1
```

Installer behavior:

- exact supported `GoW.exe` hash required;
- schema-3 build manifest required;
- unknown game-root `dxgi.dll` is never overwritten;
- existing target/manifest mismatch is refused;
- only exact owned schema-3 DXGI may be upgraded;
- previous owned DLL + manifest are backed up;
- install uses a staged temp DLL;
- `version.dll` hash must remain unchanged.

Rollback behavior:

- exact installed hash required;
- tampered DLL is refused;
- prior owned schema-3 pair is restored through a staged DLL copy;
- otherwise only the exact owned pair is removed;
- rollback receipt is schema 3;
- `version.dll` must remain unchanged.

Recovery behavior:

- unwinds only recognized schema-3 DXGI ownership chains;
- still recognizes/removes only the exact historical single-export known-bad DXGI hash:
  `2e93c9c711a5c0f622a4b977b4c8f3e4bc81f0e5b1a8640eb2946830d3d2bd2a`;
- refuses unknown/unowned game-root `dxgi.dll`;
- closed XInput production path is no longer used.

### V3 proof plumbing completed

Runner/parser changes:

- `924a9060534774d5ba8bb5976984132a615ee9a7` - DXGI proof-line parser;
- `31185935e708f70bf6a1631385356742ea0cfd5a` - DXGI runner regressions;
- `574a31ba6e0226b30852238992a8d128a111cfc3` - reversible V3 live proof runner.

V3 runtime behavior:

- target `dxgi.dll`;
- startup timeout 90 seconds;
- Steam bootstrap/successor process handling retained;
- additional 40-second main-menu settle interval, matching the user's observed ~35-second startup;
- before user action it requires fresh:
  - `RAVEN_NATIVE_BRIDGE_PROXY_LOADED target=dxgi.dll`;
  - `RAVEN_NATIVE_BRIDGE_DXGI_FORWARDED exports=20 success=true`;
  - `RAVEN_NATIVE_BRIDGE_EXE_ACCEPTED`;
- advanced-save/map-open pass then requires:
  - `RAVEN_NATIVE_BRIDGE_SNAPSHOT_ACCEPTED ... count=53 unknown=0`;
  - `RAVEN_NATIVE_BRIDGE_DELIVERY_PENDING`;
  - normal Completionist Map Script Loader evidence;
- success/failure both archive and push evidence;
- failure stops GoW before rollback;
- rollback must restore exact pre-run DXGI/manifest state;
- `version.dll` must remain byte-identical.

### Build portability and offline gate

Build-generator support:

- `a517e998aa2e3accec29ad22650cf507058259b2`
- `5f74b6c956611624f36c3f046a2a1b9270940d24`

The build script now supports both VS2022 and VS2026 CMake generators. A PowerShell regex bug in the first detector (`-split '.'`) was caught by CI and corrected to literal-dot splitting.

Dedicated offline-only local gate:

- `bdfd76e11fc0afcedea45299a8c2a8359b7cebbd`
- `tools/v0.10.5/test-raven-authority-bridge-offline-gates.ps1`

It performs:

1. runner regressions;
2. clean native build + all five CTest targets;
3. schema-3 DXGI install/upgrade/rollback/recovery testing in a temporary directory using copies of the real `GoW.exe` and `version.dll`.

It **does not install dxgi.dll into the real game directory**.

Expected success marker:

```text
RAVEN_DXGI_OFFLINE_GATES_PASSED
```

### Windows CI green

Temporary workflow was added, corrected, and then removed.

Final green workflow run:

- run ID: `35600350597`
- job ID: `106334715563`

Exact verified outputs:

```text
RAVEN_DXGI_POWERSHELL_PARSE_PASSED files=9
100% tests passed out of 5
RAVEN_NATIVE_BRIDGE_RUNNER_TESTS_PASSED target=dxgi.dll ...
RAVEN_DXGI_SECURITY_DIFF_SCAN_PASSED files=21 findings=0
```

Native CI build output:

```text
RAVEN_NATIVE_BRIDGE_BUILD_OK
dll=...\Release\dxgi.dll
sha256=2a15a23ae5f46f2973a0c2e4ea9b1db5a84f3940411a8531fb6c256aecaf9aa4
```

Temporary workflow removal:

- `38f474a3d330149b9b5000834e4cf27b67bcfd6b`

Documentation update:

- `5d53d3e9f1f128d1d48c7cdbeb5037488f70e1c3`
- `docs/research/v0105-raven-native-bridge.md`

### Current boundary

Current state:

```text
RAVEN_DXGI_LOCAL_OFFLINE_GATE_READY
```

Do **not** run the V3 live install/proof yet.

Next required action is one local offline-only gate with GoW closed.

Important local-worktree note:

- the user's local checkout may still contain Sol's uncommitted installer/rollback/recovery edits from after `e3afcad`;
- those edits were never pushed and are superseded by the remote schema-3 implementation;
- preserve them in a Git stash before hard-resetting the local branch to current origin;
- then run the offline gate.

If the offline gate passes, update this handoff with its exact output and only then advance to:

```text
RAVEN_DXGI_COMPLETE_PROXY_LOAD_PROOF_READY
```

and provide the single V3 live proof command.


## Local DXGI offline gate reported successful
The user ran the prepared offline-only gate after:

- stashing the superseded local Sol edits;
- fetching origin;
- hard-resetting the local branch to the current remote release-candidate branch;
- keeping GoW closed.

Command executed:
`tools/v0.10.5/test-raven-authority-bridge-offline-gates.ps1`

User reported:

```text
done
```

with no error indication.

This gate is intentionally local-only and does not auto-push a runtime capture, so the exact console transcript is not archived in GitHub. Based on the user's explicit success report and no reported error, treat the gate as passed.

The gate covers:

1. runner regressions;
2. clean native build and all five CTest targets;
3. schema-3 DXGI install/upgrade/rollback/recovery in a temporary directory populated from the real supported `GoW.exe` and `version.dll`;
4. no proxy installation into the real game directory.

The remote CI gate was already green for:

```text
RAVEN_DXGI_POWERSHELL_PARSE_PASSED files=9
100% tests passed out of 5
RAVEN_NATIVE_BRIDGE_RUNNER_TESTS_PASSED target=dxgi.dll ...
RAVEN_DXGI_SECURITY_DIFF_SCAN_PASSED files=21 findings=0
```

Therefore the current state advances to:

```text
RAVEN_DXGI_COMPLETE_PROXY_LOAD_PROOF_READY
```

Next action is the single reversible V3 live proof runner:

`tools/v0.10.5/run-raven-authority-bridge-load-proof-and-push.ps1`

V3 expectations:

- GoW must be fully closed before start;
- runner rebuilds and reruns offline gates;
- installs only the owned schema-3 `dxgi.dll`;
- waits through Steam handoff and the normal ~35-second startup;
- requires fresh complete-DXGI forwarding and supported-exe evidence before user action;
- user then loads the advanced Raven save, opens the map, waits at least 15 seconds, quits GoW fully, and presses Enter;
- runner requires `count=53 unknown=0` plus Script Loader evidence;
- runner rolls back exact pre-run DXGI/manifest state;
- `version.dll` must remain byte-identical;
- both success and failure evidence are archived and pushed automatically.

If the V3 proof passes, the next engineering boundary is native snapshot delivery into the existing map/compass runtime. Do not redo native load architecture or Raven authority research.


## V3 COMPLETE DXGI LIVE PROOF PASSED

Successful runtime proof:

- commit: `6023dd419959bcb0645d08a4a4259dfe56a7b07a`
- capture: `archive/field-logs/runtime-captures/raven-native-bridge-load-proof-v3-20260921-130020/`

Final result:

```text
result=RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V3_PASSED
reason=dxgi_complete_forward_startup_hash_53_state_snapshot_and_script_loader_proven
proxy_target=dxgi.dll
proxy_contract=system32-dxgi-v1
game_launched=true
rollback_exact=true
version_dll_untouched=true
bridge_process_memory_writes=false
bridge_save_writes=false
bridge_progression_writes=false
version_dll_writes=false
```

Proof checks:

```text
proxy_loaded=true
dxgi_forwarded=true
exe_accepted=true
snapshot_53_unknown_0=true
delivery_pending=true
script_loader_completionist_map_loaded=true
fresh_log_prefix_match=true
fresh_loader_log_prefix_match=false
```

The loader-log prefix mismatch is not a functional failure. Fresh Script Loader evidence was present and the proof's explicit Completionist Map loader check passed.

### Exact live bridge sequence

```text
RAVEN_NATIVE_BRIDGE_PROXY_LOADED target=dxgi.dll real=system32
RAVEN_NATIVE_BRIDGE_DXGI_FORWARDED exports=20 success=true
RAVEN_NATIVE_BRIDGE_EXE_ACCEPTED sha256=caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452
```

Steam handoff was handled correctly:

```text
bootstrap_pid=48344
bootstrap_exited=true
bootstrap_exit_code=53
startup_game_pids=29616
steam_handoff_tolerated=true
main_menu_settle_seconds=40
```

The complete proxy therefore fixes the original `CreateDXGIFactory2` loader failure and is compatible with normal GoW + Script Loader startup on the target machine.

### Authoritative Raven snapshots observed live

Before the advanced save finished restoring, the bridge briefly published:

```text
generation=1
count=53
unknown=0
alive=53
killed=0
explicit=0
absentWadFalse=53
```

One second later, after the advanced save/checkpoint authority became available, it published the exact expected state:

```text
generation=2
count=53
unknown=0
alive=26
killed=27
explicit=42
absentWadFalse=11
```

This exactly matches the accepted advanced-save fixture.

Important delivery implication:

- generation 1 is a transient valid all-false authority view while staged save state is not yet restored;
- generation 2 is the current advanced-save state;
- the delivery layer must **not blindly push the first published snapshot during boot**;
- authoritative map reconstruction should occur on map-open/current-save readiness, using the newest atomic snapshot then available;
- existing immediate loaded-Raven `ravenKilled` event behavior remains the path for instant kill removal between full authority reconstructions.

For a genuinely fresh save, all 53 alive remains the correct eventual state, so delivery logic cannot simply reject all-alive snapshots. It must use game/save/map lifecycle timing rather than state shape to decide when to synchronize.

### Native load layer CLOSED

The following are now solved and must not be revisited:

- XInput load-point selection;
- DXGI load-point selection;
- DXGI export completeness;
- `CreateDXGIFactory2` compatibility;
- System32 forwarding;
- Steam bootstrap process tracking;
- schema-3 install ownership;
- rollback/recovery;
- `version.dll` coexistence;
- native 53-state authority generation.

Current architecture status:

```text
RAVEN_NATIVE_LOAD_AND_AUTHORITY_PROVEN
```

### Next engineering boundary: snapshot delivery

The remaining release blocker is delivering the accepted native atomic 53-state snapshot into the existing Completionist Map map/compass runtime.

Required behavior remains:

1. map open reconstructs the exact 53 Raven states from the latest authoritative native snapshot;
2. old/advanced saves display only surviving Ravens;
3. fresh saves display all 53;
4. killing a currently loaded Raven removes its marker immediately through the existing `ravenKilled` event path;
5. reopening the map reasserts the exact authoritative saved/checkpoint state;
6. preserve realm/caption/compass fixes;
7. no save/progression writes.

Preferred next investigation is the already-captured native Lua binding registration evidence:

- `archive/field-logs/source-scans/native-binding-descriptors-20260914-160311`
- `archive/field-logs/source-scans/native-binding-registration-context-20260914-164815`
- `archive/field-logs/source-scans/native-binding-dispatcher-20260914-165955`
- `archive/field-logs/source-scans/native-binding-table-xrefs-20260914-161300`
- `archive/field-logs/source-scans/native-lua-binding-xrefs-20260914-065549`

Do not rerun those scans. Inspect the archived evidence first.

Preferred delivery shape:

```text
CompletionistMapNative.GetRavenSnapshot()
```

Requirements if native Lua registration is used:
- no overwrite/collision with existing binding;
- idempotent registration;
- read-only;
- no raw save/progression mutation;
- survives map reopen/load;
- returns one atomic generation of all 53 states;
- map sync consumes the newest snapshot only when current save/map lifecycle is ready.

If legitimate registration is not safely available, fall back to a native map-sync integration using known marker data/functions, still without progression writes or forced WAD loading.

Do not redo Raven authority or native load research.


## Native Raven snapshot delivery Sol task prepared

Focused implementation task:

- commit: `377ef33120299b298d3e8418fedc6d0e820d521c`
- file: `docs/research/CODEX-SOL-v0105-raven-snapshot-delivery-task.md`

This task starts after the passed V3 DXGI proof and explicitly forbids reopening solved authority/load research.

Key implementation boundary:

- keep the proven native `CompletionistMapGetRavenSnapshotV1`;
- expose the newest atomic snapshot safely to Lua or use a non-invasive native map-sync fallback;
- do not mutate/overwrite the game's existing 309-entry static native descriptor table;
- use legitimate runtime registration if safely recoverable from archived evidence;
- existing Lua `CompletionistMapV105ApplyPersistedRavenKills` is the intended state-application point;
- map-open must refresh native authority before `syncIcons`;
- retain the existing loaded-Raven `ravenKilled` event path for immediate kill removal.

Important V3 timing is carried into the task:

- a transient all-53-alive generation may exist before an advanced save finishes restoring;
- therefore readiness must be tied to map/save lifecycle timing, not snapshot shape;
- a true fresh save legitimately has the same all-53-alive shape.

Target stop state:

```text
RAVEN_NATIVE_SNAPSHOT_DELIVERY_LIVE_PROOF_READY
```

No local user action is needed until that task has produced green offline/CI gates and one reversible live acceptance runner.


## Native snapshot delivery implementation and hardened CI green

The focused Sol delivery pass completed the implementation up to the live acceptance boundary before Codex usage expired.

### Delivery architecture

Archived native-binding evidence was inspected first.

The safe conclusion was:

- the shipped native function descriptor table is fixed/sorted;
- the dispatcher bsearch uses the fixed 309-entry table;
- no safe post-startup registrar was proven;
- therefore do **not** append/overwrite/patch the existing descriptor table.

Instead the already-proven DXGI bridge exposes one read-only atomic Raven snapshot over a narrow local loopback transport, queried by Lua only when the map opens.

This preserves:

- no static descriptor writes;
- no game code-byte patching;
- no save/progression writes;
- no permanent polling;
- existing immediate `ravenKilled` event behavior.

### Native loopback endpoint

Commit:

- `6dbba17f8c8994c3191eb3494d359dd158aff222`
- message: `feat(v0.10.5): expose Raven snapshot on loopback`

Files:

- `native/raven-authority-bridge/src/snapshot_delivery.cpp`
- `native/raven-authority-bridge/src/snapshot_delivery.h`

Contract:

```text
address=127.0.0.1
port=43753
request=GET RAVEN_SNAPSHOT_V1\n
```

Native endpoint properties:

- binds only `INADDR_LOOPBACK`;
- uses `SO_EXCLUSIVEADDRUSE`;
- one fixed bounded request format;
- client recv/send socket timeouts: 250 ms;
- reads one already-atomic `NativeRavenSnapshot`;
- serializes:
  - schema;
  - generation;
  - captured tick;
  - count=53;
  - unknown=0;
  - alive/killed;
  - explicit;
  - absent-WAD-false;
  - exact killed catalogue IDs;
- if no snapshot exists yet, returns `UNAVAILABLE`;
- any bind collision/refusal fails closed for the process;
- endpoint startup is idempotent.

Native log marker:

```text
RAVEN_NATIVE_BRIDGE_DELIVERY_READY mechanism=loopback_socket address=127.0.0.1 port=43753 static_descriptor_writes=false save_writes=false progression_writes=false
```

### Lua map-open delivery

Commit:

- `512767923b82bb636dd6e9eaa35f532537588baa`
- message: `feat(v0.10.5): apply native Raven snapshots on map open`

`tools/v0.10.5/all-ravens-map-runtime.lua` now:

1. owns a private `CompletionistMapNative.GetRavenSnapshot` wrapper only if no collision exists;
2. requires `socket.core`;
3. connects only to `127.0.0.1:43753`;
4. requests one snapshot on map create/open;
5. validates:
   - schema=1;
   - generation >= 1;
   - count=53;
   - unknown=0;
   - alive+killed=53;
   - explicit+absentWadFalse=53;
   - every killed ID is a known catalogue ID;
   - no duplicate killed IDs;
   - killed-ID count matches reported killed count;
6. applies only a strictly newer generation;
7. calls existing `CompletionistMapV105ApplyPersistedRavenKills`;
8. only after authority refresh does normal map pin creation + Raven icon sync occur.

Important order:

```text
refreshNativeAuthority("map_create")
-> base CompletionistMapV100_CreateMapPin
-> syncIcons(self, "map_create")
```

No redesign of map/compass state was needed.

Existing immediate loaded-Raven event path in:

`tools/v0.10.5/all-ravens-gameplay-events.lua`

remains unchanged.

If the native accessor is unavailable, malformed, stale, or collides with another API, Lua fails closed and does not blindly clear valid event-derived Raven state.

Generation semantics are monotonic:

- newer generation: apply;
- same generation: ignore;
- older generation: ignore.

This specifically preserves an immediate event kill across a same-generation map reopen, while a newer authoritative native generation can later reassert current persisted state.

### Security hardening after formal review

Formal review found one real low-risk local DoS issue in the initial Lua client: `receive("*l")` had no response-size bound if another local process won the port first.

Fix commit:

- `a3509b6be9a168d6eda56c9343339064b3e7dc3f`
- message: `fix(v0.10.5): bound native snapshot response reads`

Current Lua receive behavior:

```text
nativeMaxResponseBytes=4096
total timeout=0.25 s
read=1 byte at a time until newline
CR rejected
oversize response fails closed
```

The normal 53-Raven wire payload is well below the 4 KiB cap.

### Offline/live proof tooling
Commit:

- `3725ea7232ec468f9270b35ef46140c6566a1963`
- message: `test(v0.10.5): prepare reversible Raven delivery proof`

Added:

- `tools/v0.10.5/test-raven-native-snapshot-delivery-offline-gates.ps1`
- `tools/v0.10.5/prepare-all-ravens-delivery-candidate.py`
- `tools/v0.10.5/run-raven-native-snapshot-delivery-live-proof-and-push.ps1`

The local offline gate was reported green by Sol after the security fix:

- native MSVC `/W4 /WX`;
- 5/5 native CTests;
- 13 Lua 5.1 tests;
- 21 runtime model tests;
- candidate/build tests;
- transaction rollback;
- PowerShell parse;
- security token gate.

### Hardened Windows CI rerun green

CI rerun commit:

- `86ccda3b643a4b689ac77502b74ef2771da71842`
- message: `ci(v0.10.5): revalidate bounded Raven delivery`

Run:

- `35619106676`
- job: `106397360584`
- conclusion: `success`

Exact verified outputs include:

```text
100% tests passed out of 5

RAVEN_NATIVE_BRIDGE_BUILD_OK
sha256=c27837aba95daa00de4faf60ff14f915c474b76d9cfe3910c0979298d6495771

RAVEN_NATIVE_BRIDGE_RUNNER_TESTS_PASSED
target=dxgi.dll
delivery_sequence=true
rollback=true

Ran 13 tests in 0.034s
OK

Ran 21 tests in 0.005s
OK

RAVEN_SNAPSHOT_DELIVERY_WINDOWS_SECURITY_PASSED
findings=0
process_writes=false
save_writes=false
progression_writes=false
static_descriptor_writes=false
bounded_response=true
```

The exact runtime-proven v3.3 build fixture is not installed on the hosted CI machine, so fixture-dependent build tests were skipped there; template/native-delivery contract tests still ran, and the full local offline gate used the real local fixture.

Temporary CI workflow was removed after the hardened rerun passed:

- `18ecbccb1fa3aff5d58644cf45a42ed0c352c923`
- message: `ci(v0.10.5): remove bounded delivery gate`

### Current boundary

Current branch state advances to:

```text
RAVEN_NATIVE_SNAPSHOT_DELIVERY_LIVE_PROOF_READY
```

The single prepared live runner is:

`tools/v0.10.5/run-raven-native-snapshot-delivery-live-proof-and-push.ps1`

It is combined and reversible:

- regenerates/pins the five-file All-Ravens map candidate;
- reruns offline gates first;
- transactionally installs the five map/runtime candidate files;
- installs the owned schema-3 DXGI bridge;
- tolerates Steam bootstrap and waits for native delivery ready;
- requires manual acceptance in this exact order:
  1. advanced save: exact 26 live / 27 killed absent + captions/realm/compass;
  2. kill one loaded live Raven: exact marker disappears immediately;
  3. close/reopen map: killed Raven remains absent;
  4. true fresh save: all 53 Ravens shown + captions/realm/compass;
- requires matching log evidence for the ordered sequence;
- asks user to quit GoW fully;
- restores the exact pre-run five game files;
- rolls back exact pre-run DXGI/manifest state;
- verifies `version.dll` unchanged;
- archives and pushes both pass and failure evidence.

Do not rerun native binding research, Raven authority research, DXGI/XInput work, or the delivery CI before the live acceptance result.


## First snapshot-delivery live attempt failed before install: candidate root mismatch

User ran the prepared live proof runner from branch state `ace97246c53cf36b5f1db2c7d6a796983028a50c`.

The runner successfully prepared the five-file delivery candidate and printed:

```text
ALL_RAVENS_NATIVE_DELIVERY_CANDIDATE_PREPARED files=5 map_sha256=d01b64e349bf9f3953dd40d70a23a2e80c1f527e9edb640218dbcaf9ebf4289f
```

It then failed immediately at its own preflight:

```text
Candidate misses: exec/dc/pc_le/mapmaster.dcb
```

This happened **before**:

- offline gates;
- transactional game-file install;
- DXGI bridge install;
- GoW launch.

Therefore this failed attempt made no live game/install changes and required no rollback.

The Python preparer and PowerShell runner intended to use the same relative candidate path, but the live machine resolved them through different canonical/worktree roots. The likely cause is worktree/junction/canonical-path divergence on Windows.

### Candidate-root normalization fix

Preparer commit:

- `bbe9b3758e37726a95cd668e549c1507c1e82aa7`
- reports the exact canonical `build.OUTPUT.resolve()` root.

Runner commit:

- `992c87d3512d74ac18cce6e1f7c6c63e9d7403fd`
- captures preparer output;
- extracts exactly one canonical candidate root;
- verifies each of the five prepared files against the pinned proof SHA;
- if the prepared root is already inside this worktree's build tree, uses it directly;
- otherwise mirrors only the five verified candidate files into this worktree's canonical build root;
- verifies destination hashes before continuing;
- emits:
  `RAVEN_DELIVERY_CANDIDATE_PATH_READY root=... files=5`.

A CI syntax-check pass caught an intermediate authoring typo where a literal `\n` was inserted into the Python source. The user never pulled that broken intermediate commit.

Correction:

- `28c85bed832d1e3bf54d88917882fac82f67ee8b`
- emits the root marker on a real separate Python line.

### Path-fix CI green

Temporary workflow run:

- run: `35621690487`
- conclusion: `success`

Verified:

```text
RAVEN_DELIVERY_PATHFIX_POWERSHELL_PARSE_PASSED
RAVEN_DELIVERY_PATHFIX_PYTHON_COMPILE_PASSED
RAVEN_NATIVE_BRIDGE_RUNNER_TESTS_PASSED ...
```

Temporary path-fix workflow removed after green:

- `337974e7a0dd3c6c969be7468569a21ac0b1d0d5`

Current boundary remains:

```text
RAVEN_NATIVE_SNAPSHOT_DELIVERY_LIVE_PROOF_READY
```

Retry the same reversible live proof runner after pulling the latest branch.


## Second snapshot-delivery live attempt failed before install: literal PowerShell newline

User retried after pulling through `739fcb14ef22db80d9915bb8c11e401b850c68b6`.

The runner failed immediately at line 33:

```text
The variable '$candidateRoot' cannot be retrieved because it has not been set.
```

Inspection of the actual branch file showed the exact bug:

```text
$worktreeCandidateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-release-candidate\offline\candidate\game-root'\n$candidateRoot = $worktreeCandidateRoot
```

The PowerShell source contained the two literal characters `\n` rather than a real newline.

This failure happened before:

- candidate verification;
- offline gates;
- transactional game-file install;
- DXGI bridge install;
- GoW launch.

Therefore the second failed attempt also made no live game/install changes and required no rollback.

### Fix

Commit:

- `ff3d8027fa4b14be8fa6a3bf75aeeee1c40e1538`
- message: `fix(v0.10.5): split candidate root assignments correctly`

The runner now has two real standalone statements:

```powershell
$worktreeCandidateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-release-candidate\offline\candidate\game-root'
$candidateRoot = $worktreeCandidateRoot
```

### Stronger assignment CI gate

The previous path-fix CI only proved that PowerShell syntax parsed, which did not catch the semantic assignment issue.

A stronger temporary Windows CI gate was added to inspect the actual PowerShell AST and require two separate `AssignmentStatementAst` nodes:

- `$worktreeCandidateRoot`
- `$candidateRoot`

Run:

- `35622305143`
- conclusion: `success`

Verified:

```text
RAVEN_DELIVERY_ASSIGNMENT_AST_PASSED
RAVEN_DELIVERY_PREPARER_COMPILE_PASSED
RAVEN_NATIVE_BRIDGE_RUNNER_TESTS_PASSED ...
```

Temporary workflow removed after green.

Current boundary remains:

```text
RAVEN_NATIVE_SNAPSHOT_DELIVERY_LIVE_PROOF_READY
```

Retry the same reversible live proof runner after pulling latest branch.


## Manual live snapshot-delivery field result: persistence works; Raven map UI regressions remain

The user completed the corrected live snapshot-delivery test and reported that the core persistence behavior worked in-game.

No new auto-pushed live-proof capture commit is present on the remote branch at this point, so this section records the user's direct field observation only and does **not** claim an archived runner pass.

Observed working behavior:

- the advanced/old save correctly omitted Ravens that were already killed;
- therefore the native authoritative snapshot -> Lua persisted-kill application -> map icon filtering path worked in the real game.

Observed remaining UI/runtime regressions:

1. selecting a live Raven did not show the expected map title:
   `Odin's Raven`;
2. the small subtitle:
   `Completionist Map`
   was also absent;
3. after adding/replacing a Raven on the compass, the map's current compass-action text did not update immediately;
4. the stale action text corrected only after another UI/hover-style refresh.

This is a **functional persistence pass with UI polish still open**, not final public-release acceptance.

### Proven source of the compass prompt regression

The generalized v0.10.5 runtime currently changes compass state in `MapOn:ShowOnCompass` but does not refresh the visible cursor-card/footer prompt afterwards.

The proven v0.10.4 v3.3 routing code had a `refreshPrompt(self, selected)` helper that:

- recomputed the Raven prompt;
- updated `MapCursorInfo -> CursorInfo_Top -> CursorAction_Text`;
- called `self.menu:UpdateFooterButton("ShowOnCompass", ...)`;
- called `self.menu:UpdateFooterButtonText()`;
- ran immediately after successful add/replace and remove.

The original v0.10.3 native Raven production code contains the same explicit comment that otherwise the text above the selected marker remains stale until hover changes.

Therefore port the proven prompt-refresh behavior into v0.10.5 rather than inventing a new mechanism.

### Raven title/subtitle boundary

The base map's `MapOn:UpdateReticleInfo(currState, markerInfo)` derives normal marker text from:

```lua
title = util.GetLAMSMsg(markerInfo.LamsNameId, markerInfo.Id)
desc = util.GetLAMSMsg(markerInfo.LamsDescriptionId, markerInfo.Id)
```

The generalized custom Raven marker currently reaches the UI without useful LAMS title/description text, explaining the blank title/subtitle.

Required fix:

- for an exact selected custom Raven only, restore:
  - title: `Odin's Raven`
  - description/subtitle: `Completionist Map`;
- do not change stock/Nornir marker title behavior;
- use the game's existing `UpdateReticleInfo` UI objects/handles rather than a global text hack;
- keep the persistence/native-authority path unchanged.

### Current next boundary

Implement and test only these UI fixes:

1. restore Raven title/subtitle on exact Raven selection;
2. port immediate compass prompt refresh after add/replace/remove;
3. keep old-save killed-Raven filtering unchanged;
4. keep realm filtering, selection identity, compass single-active behavior, and immediate `ravenKilled` path unchanged;
5. no save/progression/process writes.

Do not reopen Raven authority, DXGI/XInput, native loading, or snapshot transport research.


## Raven reticle text and immediate compass prompt UI fixed

The manual live field result proved old-save killed-Raven filtering worked but exposed three UI regressions:

- missing `Odin's Raven` title;
- missing `Completionist Map` subtitle;
- stale Add/Replace/Remove compass action text until another hover/UI refresh.

### Proven historical UI behavior recovered

The original v0.10.1 installer contains the safe Raven reticle path:

```lua
self:SetReticleInfo(
  currState,
  "Odin's Raven",
  CompletionistMapV100_Description()
)
```

The v0.10.3/v0.10.4 Raven production routing contains the proven immediate prompt refresh path:

- `MapCursorInfo`;
- `CursorInfo_Top`;
- `CursorAction_Text`;
- `UI.SetTextIsClickable`;
- `UI.SetText`;
- `self.menu:UpdateFooterButton("ShowOnCompass", ...)`;
- `self.menu:UpdateFooterButtonText()`.

Those historical mechanisms were ported rather than inventing new UI object names.

### Runtime fix

Commit:

- `f4899d9f5d510e4d9b69e640f73290d5623a7e70`
- message: `fix(v0.10.5): restore Raven reticle and live compass prompt`

Current generalized v0.10.5 behavior:

1. exact custom Raven collision is captured as before;
2. the stock collision handler still runs;
3. only if the exact custom Raven selection remains valid, v0.10.5 calls:

```lua
self:SetReticleInfo(currState, "Odin's Raven", "Completionist Map")
```

This intentionally does **not** clear `currMarkerID`, because the generalized 53-Raven exact compass ownership path depends on the actual selected marker ID.

Stock/Nornir reticle behavior is left unchanged.

For compass actions, v0.10.5 now has an immediate prompt refresh helper that updates both:

- cursor-card action text;
- footer action text.

A small per-selection intent tracks the just-requested state so asynchronous native compass-manager settlement cannot momentarily re-display the old action.
Expected immediate transitions:

```text
Add -> Remove
Replace -> Remove
Remove -> Add/Replace as applicable
```

The intent is cleared on map teardown/reset and does not affect a different selected Raven.
Persistence/native authority code was not changed.

### Regression tests

Commit:

- `2cdb7f5f850d2348db04db0af30b63d3414577d7`
- message: `test(v0.10.5): cover Raven reticle and immediate compass prompt`

Lua 5.1 tests now explicitly require:

- exact title = `Odin's Raven`;
- exact subtitle = `Completionist Map`;
- Add selection immediately shows Remove after action;
- Replace immediately shows Remove after action;
- Remove immediately shows Add when no other target remains;
- both cursor-card and footer text update;
- existing 53-Raven lifecycle/persistence behavior still passes.

### Windows UI-polish CI green

Temporary workflow run:

- `35624689900`
- job: `106416046383`
- conclusion: `success`

Verified:

```text
100% tests passed out of 5

RAVEN_NATIVE_BRIDGE_RUNNER_TESTS_PASSED
target=dxgi.dll
delivery_sequence=true
rollback=true

Ran 14 tests in 0.031s
OK

Ran 21 tests in 0.004s
OK

RAVEN_UI_POLISH_SECURITY_PASSED findings=0
```

The 14 Lua tests include the new reticle/prompt regression.

Temporary workflow removed after green:

- `b72fc33cf88ce7e1d9fec2a297dc7a80933a800d`

### Current boundary

The core authoritative filtering remains field-proven manually:

- already-killed Ravens absent on the advanced save.

Next action is one live UI regression retest using the existing reversible snapshot-delivery runner.

Required observations:

1. already-killed Ravens remain absent;
2. selected live Raven shows:
   - `Odin's Raven`
   - `Completionist Map`;
3. Add/Replace/Remove action text changes immediately without moving off the Raven;
4. compass behavior itself remains correct;
5. immediate kill removal remains correct;
6. rollback remains exact.

Do not reopen authority/load/transport research.

## Addendum 2026-09-21 22:05 - final Raven authority redesign CI green

The remaining live persistence and rapid compass-toggle regressions were traced to two distinct races and fixed on `codex/all-ravens-release-candidate`.

### Final persistence/authority model

The release candidate no longer treats a transient gameplay `ravenKilled=false` as authority.

Current rules:

- loaded Raven gameplay events are **positive evidence only**;
- `ravenKilled=true` hides that exact Raven immediately;
- `ravenKilled=false` is deferred and cannot resurrect a Raven;
- immediate event kills are retained in a separate session kill overlay;
- ordinary newer native snapshots merge that overlay instead of clearing it;
- only an explicit save/load/checkpoint authority boundary may clear the overlay;
- after such a boundary, only the first **strictly newer complete 53-Raven snapshot** may replace the previous state.

The native bridge now publishes every accepted 53-Raven capture, even when all 53 states are unchanged. Snapshot generation therefore acts as a capture-freshness token as well as a state version. This allows Lua to prove that an authority snapshot was captured after a load/checkpoint boundary without any save/progression write.

Relevant implementation commits in this pass include:

- `31dba82` - make native Raven snapshot generation a freshness token;
- `3f5137b` / `7eb713e` - atomic load-boundary reconciliation and kill-only gameplay evidence;
- `b381ad0` - forbid alive writes through the gameplay event API;
- `9ca8fe0` - preserve immediate Raven kills in a session overlay until load authority;
- `e66eaca` - mirror the session-overlay semantics in the pure runtime model.

### Final compass race fix

Rapid Add -> Remove -> Add could lose the Raven HUD target because the game may temporarily expose the newly added Raven marker ID through the stock compass query while the custom class is settling.

The final router now:

- treats the selected Raven's own marker ID as an alias, not a foreign stock target;
- removes only other stock targets such as the boat fallback;
- hides known Raven aliases by Raven name when cleanup is required;
- does not declare Add settled until the custom Raven target is positively observed;
- does not declare Remove settled until the custom target is gone and no other stock target remains.

This covers the exact live regression where the third Add produced no HUD marker.

### Final CI proof

Final temporary Windows CI run:

- run: `35642311685`
- tested head: `2163fed4a0173855a773065b5933d93c23b2e618`
- conclusion: **success**

Verified outputs:

```text
Ran 18 tests in 0.062s
Ran 23 tests in 0.005s
Ran 15 tests in 0.005s
RAVEN_NATIVE_BRIDGE_RUNNER_TESTS_PASSED ...
100% tests passed out of 5
RAVEN_FINAL_AUTHORITY_SECURITY_PASSED findings=0
```

The temporary workflow was removed immediately after the green run in:

- `da03a792799714c946329c6dbb923c3e4fedfce9`
- message: `ci(v0.10.5): remove final Raven authority gate`

Safety remains:

- no save writes;
- no progression/quest writes;
- no process-memory writes;
- no static native descriptor writes.

### Exact current boundary

The implementation is now ready for one final local candidate-proof refresh and one reversible live acceptance run.

Before live launch, refresh only the generated Raven Lua candidate pins + authority metadata using the safe proof refresher. The three binary candidate pins must remain unchanged.

The final live acceptance must verify:

1. advanced save still shows only surviving Ravens;
2. selected Raven shows `Odin's Raven` and `Completionist Map`;
3. rapid Add -> Remove -> Add leaves the Raven HUD compass marker present;
4. killing a live Raven removes it immediately;
5. close/reopen map keeps it absent in the same session;
6. checkpoint/save-load reconstruction removes exactly the killed set from authoritative state;
7. true fresh save shows all 53 Ravens;
8. rollback is exact.

Do not reopen save codec, GameObject identity, DXGI transport, or earlier Raven authority research unless this final live proof exposes a new concrete failure.

## Addendum 2026-09-21 22:09 - final live proof hardened

The final reversible live runner was strengthened after the full authority CI pass so checkpoint persistence cannot pass on manual confirmation alone.

### Machine-verifiable checkpoint requirement

`Test-RavenSnapshotDeliveryProofLines` now requires the ordered sequence:

1. advanced snapshot applied;
2. immediate `OnHitByWeapon` kill event;
3. map reopen observed;
4. explicit authority boundary observed from one of:
   - `OnRestoreCheckpoint`
   - `EVT_LoadSaveData`
   - `EVT_LoadSaveFile_Done`;
5. a later `NATIVE_AUTHORITY_APPLIED ... postBoundary=true`;
6. only then the fresh-save 0-killed / 53-alive apply.

The live runner writes these additional proof fields:

```text
checkpoint_authority_boundary_observed=true
checkpoint_postboundary_snapshot_applied=true
```

The `IMMEDIATE_OK` stage now fails unless both fields are proven by logs.

### Final runner CI

Temporary Windows workflow:

- run: `35642810342`
- tested head: `916b41bc4ee4a105b5f17fc3880529ee09d4fc86`
- PowerShell final runner parse: success
- checkpoint proof parser regression: success
- conclusion: success

The temporary workflow was removed in:

- `a1076f0c540ecab6a5a870ab26036e9f9aca8abe`
- message: `ci(v0.10.5): remove final Raven live proof gate`

Current next action remains one local proof refresh followed by the reversible live runner. No further offline research is required before field acceptance.

## Addendum 2026-09-21 23:05 - tracked transaction self-test no longer dirties live proof

A final local launch attempt was blocked before the proof runner started by the outer clean-tree preflight:

```text
Tracked worktree is not clean
```

Root cause identified:

- `test-raven-native-snapshot-delivery-offline-gates.ps1` invoked `test-all-ravens-transaction.ps1` without `-ReportPath`;
- that transaction test defaults to writing:
  `archive/all-ravens/all-ravens-transaction-self-test.json`;
- that path is tracked;
- therefore a successful previous offline gate could regenerate the report with current candidate hashes and leave the local tree dirty;
- the live proof's pass/failure evidence publishing was not at fault; this specific error occurred before the live runner began, so there was no runner evidence directory to push.

Fix:

- commit `ea1d8fa3f5fb3765fae4d3de556ea7c71b54f5cf`
- message: `fix(v0.10.5): keep Raven offline gate tree-clean`

The offline gate now:

1. allocates a unique transaction report in the OS temp directory;
2. passes it explicitly via `-ReportPath`;
3. validates `ALL_RAVENS_TRANSACTION_SELF_TEST_PASSED`;
4. removes the temporary report in `finally`.

The tracked historical self-test JSON is no longer rewritten by normal delivery/live-proof gates.

Current local cleanup rule:

- if the only tracked local modification is
  `archive/all-ravens/all-ravens-transaction-self-test.json`,
  it is safe to restore that generated report to `HEAD` before pulling;
- any other tracked modification must be inspected rather than auto-restored.


## Addendum 2026-09-22 07:35 - adversarial audit integrated; V2 load authority

The Raven release candidate passed an independent adversarial audit and the permanent fixes were integrated cleanly onto the RC.

### Clean integration

Previous RC tip:

- `28e11f01ac173ed59d3432fe61edef052aa82c43`
- preserved live-proof history:
  `test(v0.10.5): capture Raven snapshot delivery proof 20260921-174437`

Clean integration commit:

- `db2211ed6cc2089e97cdee09d490697dc09126f7`
- message: `fix(v0.10.5): integrate adversarial Raven release audit`
- exactly 28 permanent source/test/release-gate files;
- no temporary audit workflow;
- no audit plan;
- no audit-only red/green capture artifacts.

The RC branch was fast-forwarded directly from `28e11f0` to `db2211ed`.

### Critical authority correction: generation alone is NOT load authority

The earlier addendum said a strictly newer native generation after a load/checkpoint boundary could prove freshness.

That assumption is now superseded.

Adversarial analysis reproduced this race:

1. old save/checkpoint Raven state is still staged;
2. a load/checkpoint transition begins;
3. after the boundary, the periodic native worker can sample the still-old staged state;
4. that sample receives a numerically newer generation;
5. generation therefore proves capture order only, not that the sampled data belongs to the newly restored save.

The RC now uses **epoch-bound V2 capture authority**.

Normal, non-boundary map refresh still reads:

```text
GET RAVEN_SNAPSHOT_V1
```

A completed save/checkpoint boundary owns a monotonically increasing Lua epoch and requests:

```text
CAPTURE RAVEN_SNAPSHOT_V2 boundaryEpoch=<N>
```

The native bridge performs a fresh read/decode in direct response to that request and returns:

```text
RAVEN_SNAPSHOT_V2 schema=2 boundaryEpoch=<N> generation=<G> ...
```

While a load/checkpoint boundary is pending:

- periodic V1 snapshots cannot settle it, regardless of generation;
- stale/mismatched V2 epochs are rejected;
- only a complete 53-Raven V2 capture with the exact active boundary epoch can replace retained authority/session-kill state.

Load arming is also ordered:

- `EVT_LoadSaveData`: boundary pending but capture not ready;
- `EVT_LoadSaveFile_Done`: arms epoch-bound capture;
- `OnRestoreCheckpoint`: capture is armed only after the wrapped restore returns.

This is still read-only with respect to the game:

- no save writes;
- no progression/quest writes;
- no process-memory writes;
- no static native descriptor writes.

### Compass/UI adversarial fixes

Five deterministic races were reproduced and fixed:

1. rapid Add -> Remove -> Add losing the latest intent;
2. late base update overwriting settled footer/cursor text;
3. Raven A's pending prompt overwriting Raven B while the cursor moved;
4. stale Raven ownership suppressing legitimate stock target after kill;
5. stale Raven selection hijacking the next stock action after a load boundary.

The exact same-Raven rapid re-add path now remains a release-gated regression.

### Candidate proof refresh is transactional

The proof refresh path was hardened so failure cannot strand partial candidate/proof state.

Deterministic tests now cover:

- generated Lua write failure;
- candidate/proof check failure;
- blocked commit cleanup;
- staged evidence cleanup;
- failed push preserving the successful local proof commit for retry.

Proof-refresh wrapper result:

```text
RAVEN_PROOF_REFRESH_WRAPPER_TESTS_PASSED
rollback_after_check_failure=true
blocked_commit_cleanup=true
push_failure_commit_preserved=true
```

### Five-file rollback interruption proof

The existing transaction engine was confirmed resumable during rollback through a fixture-free synthetic test:

```text
RAVEN_SYNTHETIC_ROLLBACK_RESUME_PASSED
files=5 interruption=true resumed=true exact=true
```

### Owned DXGI pair is now interruption-safe

A separate release-blocking packaging defect was fixed.

Previously, interruption after restoring an older `dxgi.dll` but before restoring its matching manifest could leave:

```text
old DLL + new manifest
```

The normal recovery path could then refuse the mixed pair.

Install/rollback/startup recovery now use an owned operation journal created before destructive writes.

Recovery is fail-closed and permits only:

- the current operation SHA;
- the exact previous owned SHA recorded in the journal;
- backup files inside the Completionist-owned backup directory.

Unknown DLL or manifest state is still refused.

Synthetic proof:

```text
RAVEN_BRIDGE_OPERATION_SYNTHETIC_PASSED
mixed_pair=true
missing_target=true
absent_pair=true
unknown_dll_refused=true
unknown_manifest_refused=true
backup_scope_refused=true
```

The final live proof also requires the operation journal to be absent after rollback.

### Independent clean-integration CI

Temporary validation branch:

- `codex/raven-release-final-integration`
- clean code commit tested: `db2211ed6cc2089e97cdee09d490697dc09126f7`
- workflow-bearing descendant: `372da4cc7b994335fa19871660152cd3983897e8`
- run: `35687273046`
- conclusion: **success**

Verified results:

```text
Lua integration:                 26 passed
Pure runtime model:              25 passed
Candidate/template contract:     15 passed
Candidate/proof transaction:      4 passed
Proof-refresh wrapper:            passed
Native/live proof parser:         passed
Five-file rollback resume:        passed
DXGI operation-journal recovery:  passed
PowerShell parser:                7 files passed
Native bridge CTest:              5/5 passed
Safety scan:                      findings=0
```

The 28 permanent integration blobs were also checked byte-for-byte against the final green audit tree: mismatches = 0.

### Final remaining action

Do not reopen codec, identity, carrier, WAD, save-ring, DXGI discovery, or Raven-authority research.

The remaining task is a **single final real-game field acceptance** on the current RC:

1. refresh the pinned Raven delivery proof transactionally;
2. advanced save shows only surviving Ravens;
3. exact Raven reticle:
   - `Odin's Raven`
   - `Completionist Map`;
4. same-map rapid Add -> Remove -> Add leaves the Raven HUD target present and no boat/stock fallback;
5. killing one live Raven removes it immediately;
6. map close/reopen keeps it absent;
7. checkpoint/save reload emits a boundary epoch and accepts only matching `capture_v2` authority;
8. restored Raven set is exact;
9. genuine fresh save shows all 53;
10. five-file + DXGI rollback is exact;
11. no Raven bridge operation journal remains.

Only a concrete failure in that final field pass should reopen implementation work.


## Addendum 2026-09-22 09:16 - field hotfix passed advanced/checkpoint; fresh epoch inference fixed

Live proof artifact:

- commit: `094b761e01831462a8b71b7a0ddea4d184e82d15`
- capture: `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-20260922-060228`
- result: failed **only** because fresh-save 0-killed V2 authority was missing.

The run materially proved the field regressions fixed before the fresh transition:

- advanced save applied exact **27 killed / 26 alive**;
- loaded Raven kill crossed Lua contexts through
  `RAVEN_NATIVE_BRIDGE_KILL_NOTED`;
- same-session map reconstruction applied **28 killed / 25 alive**;
- checkpoint reload advanced to restore epoch 2;
- matching V2 checkpoint authority applied **28 / 25**;
- manual rapid same-Raven re-add / no-stock fallback acceptance passed;
- rollback was exact;
- DXGI operation journal absent;
- no process/save/progression/static-descriptor writes.

### Fresh-save failure root cause

The raw native source correctly changed to:

```text
53 alive / 0 killed
```

but a genuine fresh/new-game transition did not emit any Raven
`OnRestoreCheckpoint` bridge note.

The bridge therefore remained on restore epoch 2, and three old epoch-2 positive
kill notes from loaded Raven instances were unioned with the fresh raw snapshot,
producing **3 killed / 50 alive**.

This was not a save decoder failure and not a stale generation problem. It was
a missing process-wide new-game boundary source.

### Fresh/new-game boundary inference fix

Integrated RC commit:

- `dbe557d8c1ead3325e6fc01718434431736aac54`
- message:
  `fix(v0.10.5): infer fresh Raven restore epoch from saved-state revival`

The bridge now tracks the last authoritative raw 53-Raven base state.

Within one save/playthrough Raven progression is monotonic: a raw authoritative
`killed=true -> killed=false` transition cannot be caused by normal Raven
progression. If such a revival is observed while the bridge is still in the same
base restore epoch, the bridge infers a new restore epoch before applying the
current-epoch session overlay.

Rules:

- explicit Raven restore note already advanced epoch -> later raw revival consumes
  that existing epoch and does **not** double-step;
- no explicit restore note + authoritative revival -> bridge advances restore epoch;
- previous epoch's session-only kill notes become ineligible immediately;
- map V1 sees the new bridge restore epoch and requires matching V2 capture;
- the fresh/new-game raw 0/53 base therefore remains exactly 0/53.

Native regression covers:

```text
27 saved kills
+ one current-epoch session kill = 28
fresh raw saved authority = 0
=> inferred new restore epoch
=> old session overlay excluded
=> merged fresh result = 0 killed / 53 alive
```

It also proves:

- unchanged saved authority does not infer a boundary;
- stable fresh authority does not increment twice;
- an explicit restore followed by raw revival does not double-advance;
- duplicate Raven restore callback shortly after inference coalesces into the
  inferred epoch.

Validation:

- branch: `codex/raven-fresh-save-boundary-hotfix`
- green CI run: `35694696180`
- conclusion: **success**
- runtime/proof/rollback gates passed;
- native bridge build passed;
- native CTest **5/5 passed**;
- safety scan **findings=0**.

The clean integration tree is byte-identical to the cleaned green hotfix tree:
`8ca9fe3a1962dccc79bc65935307b94324acef96`.

Next action: refresh the offline delivery proof metadata, then rerun the final
live proof. No codec/WAD/GameObject/save research should be reopened unless the
next field evidence contradicts this model.


## Addendum 2026-09-22 10:45 - old-save false 0/53 bootstrap isolated and fail-closed

Field regression artifact:

- commit: `22b3d26020894514e3dad826dc5772c02e98c81e`
- capture:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-20260922-064207`

Observed on an older almost-complete save:

- realms known by the user to have all Ravens killed showed custom Raven markers;
- switching toward Midgard crashed the game;
- the runner failed at the first manual acceptance gate and rolled back exactly.

### Root cause

Bridge timeline:

```text
06:44:05 accepted generation=1 count=53 alive=53 killed=0 explicit=0 absentWadFalse=53
06:44:06 rejected present_wad_without_exact_state:raven_95b9c6444d479ac68207b1829d02909b
```

The first 0/53 image was therefore a transient staged-WAD warm-up image, not
authoritative fresh-save truth. The map accepted it immediately and populated
all 53 custom markers before the decoder became correctly fail-closed one
second later.

A second unsafe bootstrap assumption was also present: before any native
authority existed, unknown Raven state defaulted to visible.

### Safe bootstrap integration

Integrated RC commit:

- `687e1213c1c33e8f54d969175b6d0bd6e152c893`
- message:
  `fix(v0.10.5): fail closed until Raven authority is proven`

Validated source branch:

- `codex/raven-bootstrap-authority-hotfix`
- final validated head:
  `0646f52eb1ff0343468b08ea21a2e169b3335be5`
- CI run:
  `35698607271`
- conclusion: **success**

Permanent changes integrated byte-for-byte from the green branch:

1. Native all-false publication quarantine:
   - first `alive=53 killed=0 explicit=0 absentWadFalse=53` image is withheld;
   - it must remain accepted for at least 750 ms before publication;
   - any capture/decoder rejection resets confirmation;
   - nonzero/full authority is not delayed.

2. Map fail-closed bootstrap:
   - before the first authoritative Raven state, custom Raven markers default
     hidden instead of visible;
   - last-good authority is still retained across later load boundaries.

3. Read-only diagnostics for unresolved old saves:
   - native rejection logs now retain explicit killed IDs, explicit alive IDs,
     absent-WAD IDs, unresolved IDs, staged record count, and transient load slot;
   - map logs every RegionSummary Raven parent with
     `progress / goal / catalogueCount / safeCountMatch`;
   - diagnostics cannot create/remove markers and perform no progression writes.

Validation:

```text
Lua integration:                 31 passed
Pure runtime model:              25 passed
Candidate/template contract:     15 passed (11 fixture-dependent skipped in CI)
Candidate/proof transaction:      4 passed
Proof-refresh wrapper:            passed
Runner / rollback gates:          passed
Native bridge CTest:              5/5 passed
Safety scan:                      findings=0
```

### RegionSummary static coverage

The archived `quests.dcb` structure proves 22 Raven parent goals totaling 51.

Only two parents differ from the 53-object physical catalogue:

```text
RegionSummary_RP_Raven_Parent     target=6  catalogue=7
RegionSummary_CALS_Raven_Parent   target=1  catalogue=2
```

All other 20 parents match exactly and cover 44 physical Ravens.

The catalogue identifies both exceptional parents as containing one bonus
untracked Raven but does not prove which physical child is the bonus. Do not
invent that mapping.

Next required evidence: run the safe RC on the same older almost-complete save,
open the map long enough to emit native partial-state diagnostics plus all
RegionSummary progress/goal values, then archive/push and rollback. Use those
facts to decide whether a deterministic partial-authority constraint solver can
close old-save state without any save/process/progression writes.


## Addendum 2026-09-22 11:15 - old-save zero-marker regression reduced to lost same-epoch boundary authority

Field artifact:

- commit: `35fa4152e987b9015b9d3ad7813e48e8c42276a4`
- capture:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-20260922-074317`
- user-visible result: no custom Raven markers rendered on the older
  almost-complete save; runner was intentionally rejected and rolled back.

### What the capture proves

The fail-closed bootstrap guard behaved correctly. It did not resurrect killed
Ravens. The zero-marker result came from authority becoming unavailable later,
not from a false all-alive publication.

Bridge chronology:

```text
07:49:41.962 snapshot accepted: generation=1, alive=26, killed=27, explicit=42, absentWadFalse=11
07:49:44.744 restore boundary advanced: restoreEpoch=1
07:49:50.082 complete post-boundary capture: generation=9, alive=26, killed=27
07:50:01.464 later decoder rejection: present_wad_without_exact_state:raven_95b9c6444d479ac68207b1829d02909b
```

The map consumed the valid post-boundary image before the later unload noise:

```text
10:49:50 NATIVE_AUTHORITY_APPLIED generation=9 killed=28 alive=25
         boundaryEpoch=1 restoreEpoch=1 authority=capture_v2
```

The 28th killed Raven is the current-epoch positive kill overlay merged over
the raw saved 27-killed snapshot.

After the map script later reloaded, the bridge still knew restore epoch 1, but
the V2 API attempted a brand-new capture. One now-unloaded/present-WAD Raven was
undecodable, so V2 returned unavailable. With no map-local previous authority
after the script reload, the fail-closed policy correctly hid all Ravens.

Therefore the missing primitive was not another Raven-state heuristic. It was a
process-local retained copy of the **already-proven complete boundary snapshot**.

### RegionSummary evidence

The diagnostics also yielded a strong independent consistency check.

The 22 runtime values currently logged under the `goal` label sum to **25**.
For every one of the 22 Raven parent quests, that value exactly equals the
number of native explicit killed IDs in the rejected partial snapshot. This
strongly indicates the runtime accessor is the live completed-count value and
the diagnostic label is misleading; `progress=nil` is the accessor that did
not resolve.

The one unresolved Raven was:

`raven_95b9c6444d479ac68207b1829d02909b`

It belongs to `RegionSummary_ALF_Raven_Parent`. That parent has two physical
Ravens, runtime completed count 0, one explicit-alive child, and the unresolved
child. Alfheim is not one of the two bonus/untracked exceptional parent groups,
so a RegionSummary constraint solver would deterministically resolve this
particular unknown as alive.

That solver is retained as a validation/fallback direction only. It is not
needed for the primary regression because a complete matching-epoch V2 image
had already been captured.

### Same-epoch boundary retention fix

RC commits:

- `d5be84ffeb020feb3afa3494b18c0e465c44b3c8`
  - test interface for the process-local boundary cache;
- `28a99d988912f92500378288b2ac36aec0d99da7`
  - bridge implementation;
- `dc21594d609e1d22542fecd67bad99a2ad67e3bf`
  - native regression coverage.

Behaviour:

1. A successful V2 capture is cached as its raw 53-Raven saved-state image for
   the current restore epoch.
2. If a later V2 fresh capture fails because WAD staging is temporarily partial,
   the bridge may serve that cached image **only when the requested boundary
   epoch still exactly equals the current restore epoch**.
3. Current-epoch positive kill notes are merged at response time, not stored
   inside the cached raw base.
4. Any explicit restore-epoch advance invalidates the cache immediately.
5. Any restore epoch inferred from authoritative killed-to-alive revival also
   invalidates the cache immediately.
6. A stale epoch cannot repopulate or read the cache.
7. No game process memory, save data, progression data, or static descriptor is
   written by this mechanism.

The native test now covers same-epoch retention, overlay separation, explicit
boundary invalidation, stale-epoch refusal, new-epoch replacement, and inferred
boundary invalidation.

Validation state at this handoff update:

- GitHub direct branch commits have no attached Actions run/status;
- Windows native compile/CTest and the full offline proof gates are **pending**;
- do not claim this fix green until those local gates pass.

Next action: pull the RC locally and run the native/offline delivery gates. If
green, refresh the delivery proof and repeat the old-save live proof. The
expected field signature after map-script reload is
`RAVEN_NATIVE_BRIDGE_BOUNDARY_CACHE_HIT boundaryEpoch=1`, followed by
`NATIVE_AUTHORITY_APPLIED` and the surviving Raven markers only.


## Addendum 2026-09-22 11:35 - proof-refresh wrapper rejected a legitimate no-op

Field artifact:

- failure commit: `0caaf53974089c78e95879fca383c2eba9ae0b72`
- capture:
  `archive/field-logs/runtime-captures/raven-delivery-proof-refresh-20260922-080323`

The live proof never launched. The failure occurred inside
`refresh-raven-delivery-proof-and-push.ps1`.

Observed transcript:

```text
ALL_RAVENS_NATIVE_DELIVERY_CANDIDATE_PREPARED ...
ALL_RAVENS_NATIVE_DELIVERY_CANDIDATE_PREPARED ...
Unexpected tracked changes:
RAVEN_DELIVERY_PROOF_REFRESH_FAILED:
Proof refresh changed an unexpected tracked path.
```

There were **no paths printed after** `Unexpected tracked changes:`. The
wrapper required `git diff --name-only` to contain exactly one path, the proof
JSON. In this run the diff was correctly empty because the new work changed only
the native bridge and native tests; the pinned five-file candidate, router
contract, state contract, map hook, and event hook already matched the existing
proof exactly.

This was a wrapper guard bug, not a delivery-proof mismatch.

Fixes:

- `14e2ff49688128c6b31e5cc8307aa43ae3deee0e`
  - proof refresh now accepts either:
    - zero tracked changes, meaning the pinned proof is already current; or
    - exactly `archive/all-ravens/all-ravens-release-candidate-offline.json`;
  - any other tracked path still fails closed;
  - no-op success commits/pushes evidence with `proof_changed=false`.

- `b6c208f991d30dea4fd17318233ebe7bbd4c36ea`
  - synthetic wrapper test now covers the exact native-only no-change case;
  - existing rollback, blocked-commit, and blocked-push cases remain covered.

Next action: run the synthetic proof-refresh wrapper test locally, then rerun
the proof refresh and native live proof. The Raven boundary-cache fix itself has
not yet had its Windows native CTest/live validation because the wrapper stopped
the previous command before those stages.



## Addendum 2026-09-22 17:25 - current-checkpoint Raven authority must reconcile WAD absence with RegionSummary

Field artifact:

- capture commit: `5a114dbf`
- capture:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-20260922-080642`
- user-visible result: zero Raven markers on the advanced save; runner was rejected
  and rolled back.

### Superseding conclusion

The prior 11:15 addendum treated the earlier 27-killed V2 image as complete
authority for the current loaded checkpoint. The new capture proves that is not
safe. For the current checkpoint, the native staged table never produced a full
snapshot. Its stable partial evidence was:

```text
explicit=41
absentWadFalse=11
unknown=1
knownKilled=25
unknownId=raven_95b9c6444d479ac68207b1829d02909b
```

The one unknown Raven is in `RegionSummary_ALF_Raven_Parent`. The other
Alfheim child is explicitly alive. The live RegionSummary accessor reports
completed count 0 for the Alfheim parent.

The archived 27-killed replay fixture differs from this live 25-killed set on
exactly two IDs, both Alfheim Ravens:

```text
raven_95b9c6444d479ac68207b1829d02909b
raven_63f2a1a74274de6df3962490fb6552e9
```

Both are killed in the archived replay, while the current checkpoint has one
explicitly alive, one unresolved, and RegionSummary completed=0. Therefore that
27-killed image is stale for the current checkpoint and must not be accepted
merely because it decoded to all 53 physical catalogue rows.

This also explains the older "killed Ravens return in unloaded regions"
regression: the 11 WAD-absence defaults were being treated as authoritative
alive states. WAD absence only proves that the corresponding WAD is not staged;
it does not prove Raven alive/dead state.

### Current recovery contract

The RC now applies these rules:

1. Fresh loopback requests attempt a fresh native capture before consulting any
   previously published process-local snapshot. A stale prior save image cannot
   win simply because the new save is still partially staged.

2. Any nonzero native image containing `absentWadFalse > 0` is quarantined as
   **partial evidence**, not published as complete authority.

3. Partial wire responses carry:
   - exact known killed IDs,
   - exact native-unknown IDs,
   - exact WAD-absence IDs,
   - restore/boundary epoch,
   - explicit / absence / known counts.

4. Lua treats both native unknowns and WAD-absence rows as unresolved. It reads
   live RegionSummary completed counts and solves each parent only when the
   solution is unique.

5. For the 20 one-to-one parents, native explicit kills must equal the live
   completed count after all unresolved rows are solved.

6. The two exceptional parents remain fail-closed whenever any of their
   physical rows are unresolved:
   - `RegionSummary_RP_Raven_Parent`: target 6, physical 7;
   - `RegionSummary_CALS_Raven_Parent`: target 1, physical 2.
   Fully explicit native state is still accepted when its killed count equals
   the official completed count or completed+1 for the single bonus physical
   Raven. No bonus child identity is guessed.

7. A fully explicit nonzero 53-row native snapshot is cross-checked against all
   live RegionSummary counts before it may become map authority. This rejects a
   stale explicit image such as the archived Alfheim 2-killed state when the
   current parent reports completed=0.

8. Exact fresh/new-game `0 killed / 53 alive / explicit=0 /
   absentWadFalse=53` remains a special case. The native publication gate must
   first observe it stably for at least 750 ms; once confirmed, it does not
   depend on RegionSummary quests already being initialised.

9. Session kill notes can resolve an otherwise unresolved physical row to
   killed for the current restore epoch only. Boundary changes still invalidate
   prior session overlays and boundary caches.

10. No game-process writes, save writes, progression writes, debugger writes, or
    static descriptor writes were added.

### Runner/proof corrections

The live runner had two independent harness issues:

- dot-sourcing the old v0.10.4 transaction engine overwrote
  `$ExpectedBranch` with `codex/v104-raven-production`; the RC runner now
  restores `codex/all-ravens-release-candidate` immediately after dot-source;
- manual acceptance tokens are now case-insensitive, so `regression` is
  treated the same as `REGRESSION`.

The proof parser is no longer hard-coded to `27 -> 28`. It now records the
validated advanced-save count and requires:

```text
advanced authority:            K killed / 53-K alive
after one live Raven kill:     K+1 killed / 52-K alive
post-checkpoint V2 authority:  same K+1 / 52-K
fresh-save V2 authority:       0 killed / 53 alive
```

It accepts either `NATIVE_AUTHORITY_APPLIED` or the new
`NATIVE_AUTHORITY_DERIVED` line and still requires matching restore/boundary
epochs and ordered bridge kill/boundary evidence.

### RC implementation series

From `5a114dbf` through current head, the important changes are:

- `a68f1e82` / `1ecf0658` - preserve safe partial native decode state;
- `8d8831ea` - deliver partial snapshots over read-only loopback;
- `33fc7fc6` / `7a3697fc` - RegionSummary model and deterministic solver;
- `414860b8` - keep live proof on the RC branch and accept case-insensitive
  manual result tokens;
- `237f58c7` - quarantine nonzero WAD-absence defaults;
- `a5bfa9d4` - prefer current fresh capture over stale publication store;
- `43ce6c31` / `f1add080` - carry and parse exact WAD-absence identities;
- `a2b443a9` - reconcile complete and partial native state against live
  RegionSummary counts;
- `c4af301e` / `e2d43ce1` - count-relative live proof plus derived-authority
  proof coverage;
- `70ce8029` / `ebb7d6ca` - preserve confirmed fresh 0/53 bootstrap without
  requiring RegionSummary availability.

Current head at this handoff update: `e2d43ce154319c8297a3f10c04b4106302a8bde6`.

Validation state:

- repository-side regression coverage has been updated for partial snapshots,
  WAD-absence identities, stale RegionSummary conflicts, fresh-zero bootstrap,
  and derived proof parsing;
- direct GitHub commits still have no attached Windows Actions run;
- **local Windows Lua/Python/PowerShell/native compile + CTest gates are pending**;
- **live game validation is pending**.

Expected first successful advanced-save signature on the current checkpoint is
now approximately:

```text
RAVEN_NATIVE_BRIDGE_PARTIAL_SNAPSHOT ... unknown=1 knownKilled=25 ...
NATIVE_AUTHORITY_DERIVED ... finalKilled=25 finalAlive=28 ...
```

The exact final count is intentionally not hard-coded by the implementation. It
must be derived from the current checkpoint's native evidence plus live
RegionSummary counts. After one live Raven kill, the proof requires exactly one
additional killed Raven.

Next action: run all local offline/native gates on Windows. Only if they pass,
run the live proof on the same advanced save, then one kill/checkpoint reload,
then a true fresh save. Do not claim release readiness before that sequence is
green.


### Follow-up 2026-09-22 17:35

- `19c42a3d` adds a direct Lua regression for the WAD-absence rule: the same
  partial native bytes are not treated as alive by default; the physical Raven
  is resolved from its live RegionSummary parent count.
- Implementation/test head before this documentation commit:
  `19c42a3dd2d37bd9cba8a303f010b39cd71524c5`.
- Windows offline/native/live validation remains pending.


### Follow-up 2026-09-22 17:45 - offline Lua failure was synthetic-fixture contamination

Windows offline validation reached the Lua integration suite after all native
bridge CTests and DXGI rollback/recovery gates passed.

Observed single failure:

```text
test_partial_native_snapshot_resolves_single_alfheim_unknown_killed ... FAIL
AssertionError: None is not true
```

This was not a solver failure. The test first set
`RegionSummary_ALF_Raven_Parent=1`, then called
`partial_response(self.a)`. The helper itself called
`_set_region_counts([])`, silently resetting all synthetic RegionSummary
parents back to 0 before Lua ran. The paired "unknown alive" test passed only
because 0 was exactly its intended count.

Fix:

- `3c213b5c6d277b9d4be4a420a5276958c70596b5`
- `partial_response()` no longer mutates RegionSummary state while building a
  native wire response.
- Partial native evidence and live RegionSummary are now independent synthetic
  inputs, matching the production architecture.

Native validation from the failed run was green before this Lua fixture failure:

- runner regressions passed;
- native bridge clean build succeeded;
- CTest 5/5 passed;
- DXGI install/rollback/recovery passed;
- interrupted-operation recovery passed.

Lua suite reached 38 tests with exactly one fixture-caused failure. Re-run the
offline gates from this commit before any live game validation.


### Follow-up 2026-09-22 18:00 - Codex audit fresh-zero contradiction fixed

The limited Codex read-only audit reached two findings before quota expired.

1. Lua 37/38 with one failure:
   - this was the already-fixed synthetic helper contamination;
   - `partial_response()` had reset RegionSummary counters;
   - fixed in `3c213b5c6d277b9d4be4a420a5276958c70596b5`.

2. Fresh 0/53 bypass skipped live RegionSummary conflict checking:
   - this was a valid issue on `352c4dd`;
   - a stable native all-false image could be accepted even when a live parent
     already reported completed Ravens.

Fix:

- `f2af954d51558c657a884a07b6869a944b3f94c2`
  - confirmed fresh 0/53 still works when RegionSummary is unavailable;
  - if any available parent completed count is non-zero, the zero snapshot is
    refused with `fresh_zero_region_summary_conflict`;
  - this preserves early fresh/new-game bootstrap without allowing known live
    quest state to be overwritten by a contradictory zero image.

Regression coverage:

- `8ce50bee5eb46d2176cd0344b0042e8316071f2a`
  - zero snapshot accepted when RegionSummary is unavailable;
  - zero snapshot accepted when available parent counts are all zero;
  - zero snapshot refused when any available parent count is non-zero.

Codex quota expired before it could continue the audit. No additional Codex
findings were produced. Windows offline gates must be rerun from the current
head before the proof refresh or live game test.


### Follow-up 2026-09-22 18:20 - every top-level Raven PowerShell run must publish evidence

User requirement clarified: PowerShell validation/runtime commands used for the
Raven RC must archive their console output to Git and push it, rather than only
printing locally.

Implemented:

- `02d06bba9d02d7989934aa7d5d2568da07e6f289`
  - added
    `tools/v0.10.5/test-raven-native-snapshot-delivery-offline-gates-and-push.ps1`;
  - captures the complete offline-gate console transcript;
  - records result/error metadata and the exact tested HEAD;
  - commits and pushes evidence on both success and failure;
  - performs a fast-forward pull before testing;
  - commits only its own evidence directory.

- `c2840e4f5fa2dc02967f4aa0ae382222e9235d1d`
  - adds the new evidence publisher to the PowerShell syntax gate.

Existing proof-refresh and live-proof top-level runners already publish their
own evidence. Future commands given to the user should use the `*-and-push.ps1`
or equivalent evidence-publishing wrappers so no meaningful PowerShell test run
exists only in the local terminal.


### Follow-up 2026-09-22 18:32 - offline evidence wrapper now captures nested PowerShell output

The first successful evidence-publishing offline run produced commit
`1c245e999d3bc0a80dbf63bf1be39bda23f4bcba` and a PASS result for tested
HEAD `159b765310150dcf879da1551eb741336c298e10`, but inspection of its archived
`console-log.txt` showed that `Start-Transcript` captured only the wrapper
host output, not the nested child `pwsh` gate stream.

This did not invalidate the exit-code PASS, but it did not satisfy the user's
requirement that all meaningful PowerShell output be preserved in Git.

Fix:

- `a1df1484cc2c0f0a8c1436565fdbbb61e1c80307`
- the wrapper now pipes the nested offline-gate process through `Tee-Object`;
- full child stdout/stderr is archived separately as
  `offline-gates-console-log.txt` while still being mirrored to the terminal;
- success now requires that the child console evidence file exists and is
  non-empty.

Re-run the evidence-publishing offline wrapper from this or later HEAD so the
repository contains a complete detailed gate transcript, not only a PASS exit
code.


### Follow-up 2026-09-22 18:40 - full pushed offline gate evidence is green

Complete evidence-publishing offline run:

- evidence commit:
  `97de04f247ac76032cb82b552f630cdc416db04d`
- tested code/documentation head:
  `774d119d53f637b93f367ee5e8917ef0ab5816f0`
- evidence directory:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-092921`
- detailed nested PowerShell output is archived in:
  `offline-gates-console-log.txt`

Verified from the pushed transcript:

- Raven bridge runner regressions passed;
- clean native build passed;
- CTest 5/5 passed;
- DXGI install/rollback/recovery passed;
- interrupted bridge operation recovery passed;
- Lua integration: 40/40 passed;
- Raven state-model: 25/25 passed;
- candidate/template suite: 15 total, 4 applicable passed and 11 source-fixture-dependent tests skipped because the exact runtime-proven v3.3 source fixture is not installed;
- pinned five-file candidate preparation passed;
- five-file transaction rollback self-test passed;
- PowerShell syntax gate passed for 6 files;
- security gate passed:
  `process_writes=false save_writes=false progression_writes=false static_descriptor_writes=false loopback_only=true`.

This is the current offline-green baseline. Next meaningful step is the live GoW
Raven snapshot-delivery proof using the evidence-publishing live runner.


### Follow-up 2026-09-22 19:05 - live proof exposed validator false negative, runtime checkpoint persistence succeeded

Live evidence commit:

- `320353125e73db94da9a6a06b336b2bc31d47b8b`
- capture:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-20260922-093836`

The runner reported failure:

`Bridge kill note, +1 Raven map reconstruction, or matching V2 checkpoint authority evidence missing.`

Inspection shows the runtime itself progressed correctly through the real gameplay
kill:

- initial advanced authority: 25 killed / 28 alive;
- a pre-kill `OnRestoreCheckpoint` cycle then established 27 / 26;
- this restore cycle emitted positive kill notes for already-killed Ravens and
  must not be mistaken for the user's manual Raven kill;
- real gameplay kill:
  `source=OnHitByWeapon catalogueId=raven_642d0d164af0a5d4076e77933c549a5d restoreEpoch=1`;
- later checkpoint reload advanced bridge epoch to 2;
- matching V2 post-boundary authority reconstructed exactly 28 killed / 25 alive.

Thus the exact latest pre-hit authority was 27 / 26 and the post-checkpoint
authority was the required +1 = 28 / 25.

The false negative came from the proof parser:

1. it selected the first generic bridge kill note, which could be an
   `OnRestoreCheckpoint` / `OnStart` positive note for an already-dead
   Raven;
2. it anchored +1 to the first authority image (25 / 28), rather than the
   latest complete authority immediately before the actual `OnHitByWeapon`;
3. it required a separate non-boundary native authority refresh after manual
   map reopen, although map reopen did not necessarily request a new native
   snapshot and the runner already obtains explicit manual acceptance for the
   immediate/reopen/checkpoint sequence.

Validator-only fixes:

- `7719f84e038ffe057caf6ffe72bc56372ef1bbf0`
  - identify the tested kill from loader evidence with exact
    `source=OnHitByWeapon`;
  - require a matching native bridge kill note for the same catalogue ID and
    restore epoch;
  - compute +1 from the latest 53-state authority before that gameplay kill;
  - keep any post-kill V1/map reopen authority as an optional diagnostic;
  - require checkpoint V2 +1 and fresh-save V2 ordering for final automated
    proof.

- `e3e047e435c6ebb72961258002cd5168a2717108`
  - regression fixture reproduces restore/start kill-note noise before the
    real gameplay kill;
  - verifies 25 -> 27 pre-hit drift, gameplay baseline 27 / 26, no native
    map-reopen refresh, checkpoint 28 / 25, then fresh 0 / 53.

- `434113af99d546ce5817353c53b2961b90bccf07`
  - intermediate live gate now requires the real gameplay bridge kill and
    matching +1 checkpoint V2 authority;
  - manual `IMMEDIATE_OK` remains the explicit evidence for immediate marker
    disappearance + map close/reopen + checkpoint-reload visual behavior;
  - result metadata now records gameplay kill ID and pre-kill baseline.

No Raven runtime/native state behavior was changed by these commits. Re-run the
evidence-publishing offline gates before another live game proof.


### Follow-up 2026-09-22 19:20 - gameplay-kill proof parser fix is offline green

Evidence-publishing offline run after the live-proof validator fixes:

- evidence commit:
  `ccd5f634fb84abf43e8cbdaa9c6bda54f5bae446`
- tested head:
  `e5b53be10c326c4cb93fa295d98a5ddd86753366`
- evidence directory:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-095542`

Verified from the pushed child transcript:

- Raven bridge runner regressions passed, including the new restore-noise /
  exact `OnHitByWeapon` gameplay-kill proof case;
- native bridge CTest 5/5 passed;
- Lua integration 40/40 passed;
- Raven state-model 25/25 passed;
- candidate/template suite passed for all applicable tests;
- pinned five-file delivery candidate preparation passed;
- five-file transaction rollback self-test passed;
- PowerShell syntax gate passed;
- security gate passed with
  `process_writes=false save_writes=false progression_writes=false static_descriptor_writes=false loopback_only=true`.

No delivered game file changed in the validator-only fix series, so the existing
pinned delivery proof remains valid and does not require another proof refresh.

Next step: rerun the evidence-publishing live GoW proof. Its authority counts are
intentionally dynamic; the advanced save may now contain the Raven killed during
the previous test, and the validator anchors +1 to the latest authority
immediately before the new exact `OnHitByWeapon` event.


### Follow-up 2026-09-22 19:35 - correction: second live run proved cross-save revival, not persistence failure

Live evidence commit:

- `3278a1237a028fec6d6f7ae73ca540446be5bd25`
- capture:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-20260922-095935`

Important user clarification: after killing
`raven_642d0d164af0a5d4076e77933c549a5d`, the user intentionally loaded a
different save in which that Raven was still alive.

Therefore the observed 27 / 26 authority and the Raven being rendered alive
again were CORRECT cross-save behavior, not evidence that the kill failed to
persist.

Observed sequence:

- exact gameplay kill:
  `source=OnHitByWeapon catalogueId=raven_642d0d164af0a5d4076e77933c549a5d restoreEpoch=2`;
- later restore boundary epoch 3 reconstructed the newly loaded save as
  27 killed / 26 alive;
- map-side evidence then showed the Raven alive again:
  `STATE_DEFERRED ... reason=alive_requires_atomic_authority`,
  followed by `NATIVE_AUTHORITY_DERIVED ... finalKilled=27 finalAlive=26`,
  `ART_PREFLIGHT ... collected=false`, and
  `ART_RESULT active=true ... collectedAtRender=false`.

That is positive evidence that restore-boundary authority can clear a kill from
the previous save and reconstruct the state of another save without leaking the
old session kill overlay.

The runner failure was caused by the scripted proof expecting the next restore
to be a post-kill persistence reload, while the user deliberately exercised the
opposite cross-save-revival case.

The explicit post-kill manual-save step added in
`c906c3d68ae5256b91bd98f2c72c567d0c35c20f` remains useful, but the live
proof must now distinguish BOTH required behaviors:

1. reload a post-kill save -> Raven remains dead;
2. load a pre-kill/other save where that Raven is alive -> Raven reappears.

Do not interpret the 27 / 26 epoch-3 authority in this capture as a runtime
failure.


### Follow-up 2026-09-22 19:50 - live proof now distinguishes persistence from cross-save revival

User clarified that the second live run deliberately loaded another save in
which the just-killed Raven was still alive. Therefore the Raven reappearing
after that restore was correct and is positive evidence for save isolation.

The live proof flow now explicitly covers both directions:

1. kill one live Raven;
2. verify immediate disappearance and map close/reopen;
3. create a NEW manual save after the kill;
4. load that exact post-kill save and verify the Raven remains absent;
5. load a DIFFERENT pre-kill/older save where that same Raven is alive and
   verify it reappears;
6. load a true fresh save and verify all 53 Ravens.

Implementation:

- `b148f91877595ae1ae93eb128cf31006cbfe1a0d`
  - proof parser no longer assumes the first restore after post-kill
    persistence is the fresh save;
  - it tolerates intermediate cross-save restore boundaries and selects the
    later boundary whose matching authority is actually 0/53.

- `17c769cc3c967022de26d99d2d04fa501f8ac110`
  - live runner adds explicit `CROSSSAVE_OK` manual acceptance;
  - result metadata records `cross_save_revival_manual`.

- `d493891a5ca026449da1688ed5e675c17e41f2fc`
  - regression fixture includes an intermediate non-fresh cross-save boundary
    before the fresh 0/53 boundary.

The runtime behavior from capture
`3278a1237a028fec6d6f7ae73ca540446be5bd25` must NOT be described as a
persistence failure. It demonstrated correct revival from a different save.


### Follow-up 2026-09-22 20:05 - dual save-load live-proof tooling is offline green

Evidence-publishing offline run:

- evidence commit:
  `9d45a0561cac38740002a55277ddfb0f203a1290`
- tested head:
  `fba82dc8bafad6941edbcbaa87ada068e05b44d0`
- evidence directory:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-101616`

Verified from pushed child console:

- Raven runner regressions passed, including restore-noise, exact
  `OnHitByWeapon`, cross-save intermediate-boundary, and fresh-V2 ordering;
- native CTest 5/5 passed;
- Lua integration 40/40 passed;
- state model 25/25 passed;
- candidate/template applicable tests passed;
- five-file candidate preparation passed;
- transaction rollback self-test passed;
- PowerShell syntax gate passed;
- security gate passed with
  `process_writes=false save_writes=false progression_writes=false static_descriptor_writes=false loopback_only=true`.

The CMake `Check size of off64_t - failed` line is only a capability probe;
CTest still reports 100% pass.

Next step is the corrected live sequence:
advanced save -> manual kill -> post-kill manual save reload (dead) ->
different pre-kill save (alive again) -> true fresh save (0/53).


### Follow-up 2026-09-22 20:35 - all live Raven behavior passes except fresh bootstrap; exact stale-overlay cause fixed

Live evidence commit:

- `6a5904a34d71b0ee82b92b83ac2e936f94fccc68`
- capture:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-20260922-102157`

User-reported result:

- advanced-save Raven set correct;
- custom captions / artwork / realm behavior correct;
- same-Raven Add -> Remove -> Add correct, no stock boat marker;
- immediate kill disappearance correct;
- post-kill manual-save reload kept the Raven dead;
- loading another pre-kill save correctly brought that Raven back;
- only remaining defect: true fresh save displayed no Raven markers.

The pushed logs isolate the fresh defect:

- native bridge confirmed a stable raw fresh image:
  `RAVEN_NATIVE_BRIDGE_SNAPSHOT_ACCEPTED ... alive=53 killed=0 explicit=0 absentWadFalse=53`;
- later V2 boundary capture also had raw 53 alive / 0 killed;
- Lua rejected the response with
  `NATIVE_AUTHORITY_UNAVAILABLE reason=response_counts`;
- all live RegionSummary parents reported completed=0.

Root cause:

Two positive session kill notes from the previously loaded save remained in the
same bridge restore epoch. When merged into the raw fresh 0/53 snapshot they
replaced two absence-default rows, producing the recognizable wire shape:

- alive=51;
- killed=2;
- explicit=0;
- absentWadFalse=51.

The old full-snapshot parser required
`explicit + absentWadFalse == 53`, so this safe-to-diagnose fresh-zero base
never reached the already-existing RegionSummary fresh-zero veto.

Fix:

- `c07acea9a2d532693cbf6948dce7483bd6a13609`
  - full parser recognizes only the exact zero-base-overlay shape where
    `explicit == 0`,
    `alive + killed == 53`, and
    `absentWadFalse + killed == 53`;
  - full authority validation independently checks RegionSummary;
  - if any live parent completed count is nonzero, normalization is refused;
  - otherwise overlay-only kills are discarded and the authority applied as
    raw fresh 0/53;
  - normal/non-fresh full snapshots keep the strict existing rules.

- `37f7152dfddc941881455fe578c98c8a2905f71c`
  - regression: V2 fresh boundary carrying two stale previous-save overlay
    kills must normalize to zero collected and reveal all catalogue rows;
  - regression: the identical wire shape must fail closed when a live
    RegionSummary parent reports a nonzero completed count.

This changes delivered `mapmenu.lua`, so the pinned delivery proof must be
refreshed before the next full offline gate run.


### Follow-up 2026-09-22 20:50 - fresh-overlay fix proof refreshed and offline green

Delivery proof refresh:

- commit:
  `137078e13a6be45ed9dad60260972070f8f72406`
- result:
  `RAVEN_DELIVERY_PROOF_REFRESH_PASSED`
- refreshed delivered map SHA-256:
  `e3f8cbe209e52f2ec96815c9700b0d7574eeba0a98658b765f67c71a4f710db8`
- source-game rebuild remained false and non-generated binary pins unchanged.

Full evidence-publishing offline run:

- evidence commit:
  `906b75b1f77e0f1f5785a59c99ad5c1e7a0490f5`
- tested head:
  `137078e13a6be45ed9dad60260972070f8f72406`
- evidence directory:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-103804`

Verified from pushed child console:

- native CTest 5/5 passed;
- Lua integration 42/42 passed;
- both fresh stale-overlay regressions passed:
  - fresh V2 overlay shape normalizes when RegionSummary is zero;
  - identical shape is vetoed when any live parent completed count is nonzero;
- Raven state-model 25/25 passed;
- candidate/template applicable tests passed;
- candidate preparation and transaction rollback passed;
- PowerShell syntax gate passed;
- security gate passed with
  `process_writes=false save_writes=false progression_writes=false static_descriptor_writes=false loopback_only=true`.

The only remaining required field confirmation is that a true fresh save now
receives and renders the 0/53 authority instead of showing no Raven markers.


### FINAL RAVEN ACCEPTANCE 2026-09-22 - all required behaviors field-proven

User final field report after the fresh-overlay fix:

- fresh save: correct;
- cross-save transition: correct;
- older save: correct;
- newer save: correct;
- previously proven advanced-save state, custom Raven artwork/captions/filter,
  same-Raven Add -> Remove -> Add, immediate kill disappearance, and post-kill
  save reload remain correct.

Final fresh-fix live evidence:

- capture/evidence commit:
  `e522268e45bdd0d8f966bdb7ddf336eb344cad7d`
- capture:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-20260922-104411`
- native bridge:
  `RAVEN_NATIVE_BRIDGE_SNAPSHOT_ACCEPTED generation=1 count=53 unknown=0 alive=53 killed=0 explicit=0 absentWadFalse=53`
- Lua:
  `NATIVE_AUTHORITY_APPLIED generation=8 killed=0 alive=53 explicit=0 absentWadFalse=53 postBoundary=false boundaryEpoch=0 restoreEpoch=0 authority=latest_v1`

The runner result file for this final session remains FAILED and must not be
rewritten: this run was used as a verification pass across existing saves and
did not include a new exact `OnHitByWeapon` event in the runner's mandatory
scripted order. Its automated failure is therefore a sequencing/proof-harness
mismatch, not a field behavior failure.

The preceding live capture
`6a5904a34d71b0ee82b92b83ac2e936f94fccc68` already proved the complementary
non-fresh behaviors in the scripted sequence:

- real `OnHitByWeapon` kill observed;
- immediate Raven disappearance manually accepted;
- post-kill manual-save reload accepted and matching +1 V2 authority observed;
- cross-save revival manually accepted;
- same-map Add -> Remove -> Add manually accepted with no stock-marker fallback.

That prior run failed only at fresh bootstrap, which was the exact defect fixed
by `c07acea9a2d532693cbf6948dce7483bd6a13609` and then proven in the final
capture above.

Together, the two immutable pushed live captures plus the final user field
acceptance prove the Raven RC requirements:

1. fresh save exposes all 53 physical Ravens;
2. existing saves expose only surviving Ravens;
3. a killed Raven disappears immediately;
4. post-kill save reload keeps it absent;
5. switching to a save where that Raven is alive revives it correctly;
6. switching among older/newer saves reconstructs each save independently;
7. same-Raven Add -> Remove -> Add retains the custom Raven marker/artwork;
8. custom captions/artwork/realm filtering remain correct;
9. no process-memory, save, progression, or static-descriptor writes are used.

Offline release baseline remains:

- delivery proof refresh:
  `137078e13a6be45ed9dad60260972070f8f72406`;
- offline evidence:
  `906b75b1f77e0f1f5785a59c99ad5c1e7a0490f5`;
- native CTest 5/5;
- Lua 42/42;
- Raven state model 25/25;
- transaction / PowerShell / security gates all green.

ALL-RAVENS RC is field-accepted. Further collectible implementation should
remain on the separate all-collectibles branch; do not contaminate this Raven
RC branch with broad collectible work.


### Raven cosmetic polish branch 2026-09-22 - footer immediacy + same-UID artwork ownership

Functional Raven RC remains frozen at:

- branch: `codex/all-ravens-release-candidate`
- accepted functional baseline:
  `056f30a01baf938423ac1f738efb540795600d53`

Cosmetic work is isolated on:

- branch: `codex/all-ravens-cosmetic-polish`
- created directly from the accepted functional baseline.

User-reported polish defects:

1. on a newly opened map, adding the first custom Raven to the compass does not
   always update the bottom-row Add/Remove text immediately;
2. Add -> Remove -> Add on the same Raven can let the stock/boat-dock artwork
   temporarily win over the custom Raven artwork until another marker is
   selected and the Raven is re-added.

UI-only fixes:

- `305227e5199ea2ed0467917a5f59a9ad7d185330`
  - immediate prompt refresh now accepts the exact committed `promptIntent`
    as owner even if the base map clears `currMarkerID` after the action;
  - when a same-UID stock entry races the custom Raven after re-add, the custom
    `CompletionistRaven` class is reasserted as the final writer immediately;
  - one bounded settlement reassert is allowed while the same-UID stock entry
    remains;
  - no authority, RegionSummary, native bridge, save, kill-state, or
    persistence logic changed.

Regression coverage:

- `06facccd3c1a7052e7975c1f285d304640ce4596`
  - first Add must refresh cursor/footer to Remove immediately even when the
    synthetic base map clears `currMarkerID` during ShowMarker;
  - same-Raven Add -> Remove -> Add race now requires at least one custom-class
    final-writer reassert and keeps `CompletionistRaven` as the final shown
    class.

Evidence wrapper support for the polish branch:

- `0e98a5fcd53e5b072114e13b01ac3ef166e04161`
  - proof-refresh wrapper accepts an explicit expected branch;
- `f2d7480ba16cb89185f15d90e2a193d888f4aff0`
  - offline evidence wrapper accepts an explicit expected branch.

Next step: refresh the pinned five-file proof on the cosmetic branch and run the
full evidence-publishing offline gates. Only after those pass should the two
cosmetic interactions be field-checked in GoW.


### Cosmetic polish follow-up 2026-09-22 - proof refreshed; offline wrapper branch parameter fixed

User ran the cosmetic-branch proof refresh successfully:

- proof refresh commit:
  `f50bfdc7ea88ce55e2bceb8ad0bfa1c79cd8e3d5`;
- delivered map SHA-256:
  `09699476a007250ed28e307347054147a8619c8f38a648bc167c46a703eaa01b`;
- proof evidence directory:
  `archive/field-logs/runtime-captures/raven-delivery-proof-refresh-20260922-111730`.

The following offline wrapper invocation then failed before running tests because
the cosmetic-branch parameterization patch had removed the hard-coded
`$ExpectedBranch` assignment without successfully adding the parameter under
`Set-StrictMode`.

Fixes:

- `75db26a101adad3a04f4fb5af3121849413ee902`
  - outer evidence wrapper now declares `-ExpectedBranch`;
  - passes the same value into the inner offline gate.

- `4c25b9ffcbf78ed00ffcbffd74e7c115ff0d5cd5`
  - inner offline gate now also declares `-ExpectedBranch`;
  - removes its fixed RC-branch assignment.

The preflight failure itself is archived from the user's terminal report:

- `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-1117-preflight/console-log.txt`;
- matching `result.txt` records that no offline tests started.

Next step is only to pull the cosmetic branch and rerun the offline evidence
wrapper with `-ExpectedBranch codex/all-ravens-cosmetic-polish`. The delivery
proof refresh does NOT need repeating.


### Cosmetic polish follow-up 2026-09-22 - second offline preflight failure fixed

Evidence commit:

- `ec388130df14c993a9a49c2e1811acbf2f29e3b0`
- evidence directory:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-112318`
- result:
  `RAVEN_NATIVE_SNAPSHOT_DELIVERY_OFFLINE_GATES_FAILED`.

The evidence wrapper and inner snapshot-delivery gate accepted the cosmetic
branch correctly, but stage 1/8 failed before native tests because
`test-raven-authority-bridge-offline-gates.ps1` still hard-coded
`codex/all-ravens-release-candidate`.

Fixes:

- `926ba9a52e837b926d178c6b3631584299ee1a7d`
  - snapshot-delivery offline gate passes `-ExpectedBranch` into the bridge
    offline gate.

- `50ecda762c1e58ef5c0ea3dc691d0cf3222c5cd8`
  - bridge offline gate declares `-ExpectedBranch` and no longer hard-codes
    the RC branch.

The four scripts invoked below that bridge gate were checked and do not contain
the same branch hard-pin. The proof refresh at
`f50bfdc7ea88ce55e2bceb8ad0bfa1c79cd8e3d5` remains valid and does not need
to be repeated.

Next step: pull the cosmetic branch and rerun only the evidence-publishing
offline wrapper.


### Cosmetic polish follow-up 2026-09-22 - offline green; cosmetic-only live proof added

Successful evidence-publishing offline run:

- evidence commit:
  `6e0e592e6c9453ed95dd64630f3929e25aea39ad`
- tested head:
  `8c36843aa5b4871cba253f3aa62754e142d3bcfb`
- evidence directory:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-112536`.

Verified from pushed child console:

- Raven bridge runner regressions passed;
- native CTest 5/5 passed;
- Lua integration 43/43 passed;
- `test_first_add_refreshes_footer_even_if_base_clears_marker_owner` passed;
- `test_same_raven_add_remove_keeps_compass_empty_and_prompt_settled` passed;
- Raven state model 25/25 passed;
- applicable candidate/template tests passed;
- transaction rollback passed;
- PowerShell parse passed;
- security gate passed with
  `process_writes=false save_writes=false progression_writes=false static_descriptor_writes=false loopback_only=true`.

Short live-proof support:

- `073918ba2734992b3bc5b6aeb2aaf11c36934ef6`
- existing transactional live runner now accepts:
  - `-ExpectedBranch`;
  - `-CosmeticOnly`.
- cosmetic-only mode keeps the same candidate/bridge install, startup readiness,
  log capture, exact rollback, and Git evidence publication, but asks only for:
  1. first selected Raven after map open: Add -> bottom-row text must change to
     Remove immediately without moving selection;
  2. same Raven: Remove -> Add -> custom Raven artwork must remain final owner,
     with no boat-dock artwork takeover.
- full Raven state/persistence/fresh-save prompts are skipped because they are
  already field-accepted on the frozen functional RC.

No delivered game file changed after proof refresh
`f50bfdc7ea88ce55e2bceb8ad0bfa1c79cd8e3d5`, so another delivery-proof refresh
is not required before this cosmetic-only live run.


### Cosmetic polish field regression 2026-09-22 - first attempt rejected; safer UI ownership fix

Failed cosmetic-only live evidence:

- evidence commit:
  `1855eea85482343c904a9e4f74d272ae2c215fb7`;
- capture:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-20260922-112900`;
- result:
  `RAVEN_NATIVE_SNAPSHOT_DELIVERY_LIVE_PROOF_FAILED`;
- reason:
  `Raven cosmetic regression reported.`;
- rollback remained exact and all write-safety flags remained false.

User field observations:

1. the intended cosmetic issues were not fixed;
2. a new regression appeared: after adding the custom Raven, the
   `Remove from Compass` action text became stuck to the floating map cursor.

Cause of the new regression:

The first cosmetic patch allowed the committed `promptIntent` to bypass the
normal cursor-selection ownership check inside `refreshPrompt()`.
`refreshPrompt()` writes both the bottom footer and
`MapCursorInfo/CursorAction_Text`, so a consumed selection could keep forcing
floating cursor text.

The first same-UID artwork reassert approach also did not solve the real
boat-dock presentation takeover.

Replacement implementation:

- `fe1baf25d615328f82a529f8971edc4772ce440b`
  - restored the map UI runtime to the accepted functional Raven baseline
    before applying the new cosmetic fix;
  - added a committed-action footer-only refresh path that never writes
    `MapCursorInfo`;
  - custom Raven tracking now keeps `currShownMarkerID=nil`, because that
    field belongs to the stock map-compass presentation path and can let the
    stock/boat artwork reclaim the same UID.

- `952f9762a73c1906bbb0f25b14cc79bbdd2af27c`
  - preserves normal floating cursor updates while the Raven is genuinely
    selected;
  - once base selection ownership is consumed, only the footer-only path may
    refresh.

Regression coverage:

- `1cd3335ad4797f6a033f16e3cb11f02fea33c122`
  - first Add with base `currMarkerID` consumed must update the footer to
    Remove immediately while leaving seeded floating cursor text untouched;
  - same Raven Add -> Remove -> Add must keep `currShownMarkerID=nil` and
    resolve the synthetic artwork owner as custom even when a same-UID stock
    entry exists.

Functional Raven authority/save/native logic remains identical to the accepted
RC baseline. The delivery proof must be refreshed again because generated
`mapmenu.lua` changed.


### Cosmetic polish follow-up 2026-09-22 - footer-only fix caught one newer-selection edge case

Proof refresh succeeded at:

- `3600381ee50ea191453f9d082492233c618fc0c4`.

Offline evidence then failed at:

- `8e1b2cce2b1d90f7a503205e58bc6f3211efc25f`;
- evidence directory:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-114043`.

Important result: both new cosmetic regressions passed:

- `test_first_add_refreshes_footer_without_sticking_cursor_text`;
- `test_same_raven_readd_keeps_stock_presentation_state_clear`.

The single failure was the pre-existing regression:

- `test_pending_action_does_not_overwrite_other_raven_prompt`.

Cause:

After tracking Raven A, moving the cursor to Raven B leaves A's settlement
`promptIntent` alive. The new footer-only watchdog could still redraw A's
`Remove` footer even though Raven B had become the current exact map
selection.

Fix:

- `bcd7a72b0ad63f41b786b0c1a5986a1f22cb8ede`
  - `refreshCommittedFooter()` now checks `currentSelection(self)`;
  - if another Raven currently owns selection, the older committed intent
    yields and performs no footer write.

This preserves the intended rules:

1. committed action may refresh the footer after base selection is consumed;
2. it may never force floating cursor text without live selection ownership;
3. it may never overwrite a newer Raven selection.

Generated `mapmenu.lua` changed again, so proof refresh and full offline gates
must be rerun before the next cosmetic-only field test.


### Cosmetic polish follow-up 2026-09-22 - newer-selection handoff completed

Proof refresh succeeded at:

- `30fc7e538edaba9ce168d4c99bb3d83232dea97d`.

Offline evidence then failed at:

- `1996a60a73323abd6b9d46d2cd5f2b8b2df4673b`;
- evidence directory:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-114418`.

Both field-shaped cosmetic regressions still passed:

- `test_first_add_refreshes_footer_without_sticking_cursor_text`;
- `test_same_raven_readd_keeps_stock_presentation_state_clear`.

The only failing regression remained:

- `test_pending_action_does_not_overwrite_other_raven_prompt`.

The previous fix correctly stopped Raven A's committed footer intent from
overwriting Raven B after selection moved, but it yielded without refreshing
Raven B after the synthetic base update, leaving `base-stale` instead of B's
expected `Replace` prompt.

Fix:

- `f50eb377fe27d86b6da9031bcffaebaf70842026`
  - `refreshCommittedActionUi()` now detects a newer exact Raven selection;
  - that newer Raven receives the normal selection-owned `refreshPrompt()`;
  - the older committed intent then stops immediately.

This restores the intended ownership transfer:

1. same selected Raven -> normal cursor + footer refresh;
2. consumed selection -> committed footer-only refresh;
3. newer Raven selection -> full UI ownership transfers to the newer Raven.

Generated `mapmenu.lua` changed, so proof refresh and offline gates must be
rerun once more before field testing.


### Cosmetic polish follow-up 2026-09-22 - clean offline baseline after prompt ownership fixes

Delivery proof refresh:

- `b37f7a6680e45b551733afdd80de057870d75fef`.

Successful evidence-publishing offline run:

- evidence commit:
  `13b66c84d975cbdbe65abd2636fdb6f9b8f78309`;
- tested head:
  `b37f7a6680e45b551733afdd80de057870d75fef`;
- evidence directory:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-114956`.

Verified green:

- Raven bridge runner regressions passed;
- native CTest 5/5 passed;
- Lua integration 44/44 passed;
- field-shaped cosmetic regressions passed:
  - `test_first_add_refreshes_footer_without_sticking_cursor_text`;
  - `test_same_raven_readd_keeps_stock_presentation_state_clear`;
- selection ownership regression passed:
  - `test_pending_action_does_not_overwrite_other_raven_prompt`;
- existing same-Raven settlement regression passed;
- Raven state model 25/25 passed;
- candidate/template applicable tests passed;
- transaction rollback passed;
- PowerShell syntax passed;
- security gate passed with
  `process_writes=false save_writes=false progression_writes=false static_descriptor_writes=false loopback_only=true`.

The cosmetic branch is ready for the short `-CosmeticOnly` field proof again.
No full Raven persistence/fresh-save repetition is required.


### Cosmetic polish field report 2026-09-22 - sticky cursor fixed; rapid re-add race and footer immediacy remain

Latest cosmetic-only live capture:

- evidence commit:
  `2847dda590d8916c175326538caf025056f4f8d4`;
- capture:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-20260922-115230`;
- runner result says `RAVEN_COSMETIC_POLISH_LIVE_PROOF_PASSED` because
  `COSMETIC_OK` was entered during the scripted check.

That result is superseded by the user's immediate post-run field report:

- sticky floating cursor text is fixed;
- footer text still does not update immediately on the first Add;
- boat-dock artwork can still appear if Add -> Remove -> Add is performed in
  very quick succession (roughly three clicks in under two seconds);
- the same sequence with longer pauses does not reproduce the boat artwork.

Log timing confirms normal slower cycles always reach
`PROMPT_SETTLED state=untracked` before the next Add. The field-only failure is
therefore the third click arriving while removal settlement is still in flight.

Replacement fix:

- `b6ea70e1dda98b093923143ac81e2604bdd1e763`
  - Add/Remove now always perform the committed footer-only refresh directly on
    the action click;
  - committed footer makes the exact action the final footer writer after the
    stock `UpdateFooterButtonText()` redraw;
  - rapid same-Raven Add received while the previous Remove is unsettled is
    queued instead of creating a second overlapping target;
  - remove settlement now also clears same-UID stock state;
  - queued Add is applied only after custom + stock state is clean, then
    recreates `CompletionistRaven` with `currShownMarkerID=nil`.

Regression update:

- `581d5ccd235e285937d136c04549f8e8381f9041`
  - rapid third click is required to queue;
  - custom Raven is required to appear only after removal settlement;
  - slower settled Remove -> Add remains immediate;
  - normal first Add must log the committed-footer path.

Live-proof prompt update:

- `49a78d8b7f6b882712899531b051f431e1a67820`
  - `-CosmeticOnly` now explicitly requires:
    1. immediate footer update;
    2. no sticky floating cursor text;
    3. deliberate rapid Add -> Remove -> Add stress;
    4. normal slower Remove -> Add.

The functional Raven RC remains untouched. Generated `mapmenu.lua` changed,
so delivery proof refresh + full offline gates are required before the next
field check.


### Cosmetic polish follow-up 2026-09-22 - queued re-add offline mismatch corrected

Delivery proof refresh succeeded at:

- `bf67c1d7601a2297db20a608470743b401528d70`.

Offline evidence failed at:

- `583e0833e1e884d4b5324e351aaa2125d4644249`;
- evidence directory:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-120836`.

Native bridge remained fully green (CTest 5/5). Lua had exactly two failures:

1. `test_rapid_readd_wins_delayed_native_remove`
   - queued rapid re-add delayed physical ShowMarker correctly, but the logical
     tracked catalogue owner had been cleared by Remove and was not reclaimed
     until the later physical re-add;
   - existing delayed-remove regression requires the new Add intent to own the
     Raven immediately so a late native/base remove cannot win.

2. `test_raven_reticle_and_compass_prompt_refresh_immediately`
   - the previous change forced every action through footer-only refresh, so a
     normally still-selected Raven no longer got its expected floating
     selection-owned Remove prompt.

Correction:

- `afa7bba29921b0fffbca1c3cd6b4aebb5c27d865`
  - queued rapid re-add now immediately restores
    `CompletionistMapV105TrackedCatalogueId`, sets custom ownership, and keeps
    `currShownMarkerID=nil`;
  - only the physical `ShowMarker` remains deferred until removal is clean;
  - queued physical re-add may execute on the first frame where custom and
    stock state are clean instead of waiting for the normal three-frame remove
    settle threshold;
  - normal selected Add/Remove first runs the selection-owned cursor+footer
    refresh, then performs one committed footer-only write as the final footer
    writer;
  - consumed-selection cases still remain footer-only, preserving the sticky
    cursor fix.

No authority/save/native state logic changed. Generated `mapmenu.lua` changed
again, so delivery proof refresh + full offline gates are required before the
next live cosmetic stress test.


### Cosmetic polish follow-up 2026-09-22 - queued rapid re-add baseline green offline

Delivery proof refresh:

- `3ec78087cba91274d353ad32801b0f0d5eeb49b2`.

Successful evidence-publishing offline run:

- evidence commit:
  `7cfb6df425af9569716cb218027f284d4d681ab8`;
- tested head:
  `3ec78087cba91274d353ad32801b0f0d5eeb49b2`;
- evidence directory:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-20260922-121240`.

Verified green:

- native CTest 5/5;
- Lua integration 44/44;
- Raven state model 25/25;
- transaction rollback;
- PowerShell syntax;
- scoped security gate.

The previously failing queued-readd regressions now pass:

- `test_rapid_readd_wins_delayed_native_remove`;
- `test_raven_reticle_and_compass_prompt_refresh_immediately`.

Field-shaped cosmetic regressions also pass:

- `test_first_add_refreshes_footer_without_sticking_cursor_text`;
- `test_same_raven_readd_keeps_stock_presentation_state_clear`;
- `test_same_raven_add_remove_keeps_compass_empty_and_prompt_settled`;
- `test_pending_action_does_not_overwrite_other_raven_prompt`.

The cosmetic branch is ready for another short `-CosmeticOnly` field stress run,
with the live prompt now explicitly requiring the fast Add -> Remove -> Add
three-click case.


### Cosmetic polish field stress 2026-09-22 - capture exposes real-vs-synthetic routing mismatch

Latest cosmetic stress capture:

- evidence commit:
  `e343fe5b3e3ce14c19b527472d00936e4d57b4b5`;
- capture:
  `archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-20260922-121825`;
- result:
  `RAVEN_NATIVE_SNAPSHOT_DELIVERY_LIVE_PROOF_FAILED`;
- reason:
  `Raven cosmetic regression reported.`;
- rollback exact; no save/progression/process/static-descriptor writes.

User field report:

- footer still does not visibly update immediately;
- sticky cursor remains fixed;
- rapid Add -> Remove -> Add still produces boat artwork;
- slow Add -> Remove -> Add works perfectly.

Important runtime evidence:

- first handled Add at 15:22:05:
  - `SHOW ... replacedStockCount=0`;
- during later interaction the exact Raven repeatedly reaches
  `SELECT_DISARM reason=prompt_owner_mismatch`;
- no `READD_QUEUED` or `READD_APPLIED` occurs anywhere in the real capture;
- at 15:22:26 v0.10.5 handles another Add as a fresh `SHOW`, with
  `replacedStockCount=1`.
- therefore the field failure does not take the synthetic queued-readd path at
  all. At least one rapid click is leaving v0.10.5 prompt/action ownership and a
  stock target exists by the time the later custom Add is handled.
- slow path is visible later:
  - 15:23:49 `REMOVE` followed by `PROMPT_SETTLED state=untracked`;
  - 15:24:07 `SHOW ... replacedStockCount=0` followed by tracked settlement.

Footer evidence:

- `FOOTER_REFRESH_COMMITTED` is emitted on the same second as `SHOW`, yet
  the user still sees stale footer text.
- therefore logging proves our write call occurs, but not that it survives the
  game's later UI redraw or becomes the rendered footer for that frame.

Capture limitation now identified:

The current live logger does not explicitly record the stock/base
`previousShow` delegation path after v0.10.5 loses prompt ownership, nor does
it capture rendered pixels/raw input. Before another behavioral patch, add
logging-only instrumentation around ShowOnCompass entry/ownership/delegation and
before/after custom+stock target sets so the exact rapid-click escape path is
field-proven instead of inferred.


### Cosmetic polish routing instrumentation 2026-09-22 - field proof gate before behavior change

Continuation point:

- prior field evidence: `e343fe5b3e3ce14c19b527472d00936e4d57b4b5`;
- prior interpretation/handoff: `521de80eeb1325176dc25b5d8ca5ad8a1a1abbf1`;
- branch remains `codex/all-ravens-cosmetic-polish`.

The field capture proved the synthetic queued-readd theory was not the real rapid-click path:

- rapid interaction reached `SELECT_DISARM reason=prompt_owner_mismatch`;
- no `READD_QUEUED` or `READD_APPLIED` occurred;
- the later custom `SHOW` reported `replacedStockCount=1`, proving a stock target had already won before v0.10.5 regained control;
- slow Add -> Remove -> Add remained clean.

Logging-only source instrumentation:

- `0307ec05145c378d91ee8845d3d7e1fa8665541e`
  - adds `PROMPT_OWNER_MISMATCH` with exact base prompt state, `currMarkerID`, `currShownMarkerID`, tracked catalogue owner, prompt intent, base selection flags, and custom/stock target sets;
  - adds `SHOWONCOMPASS_ENTRY`;
  - adds `SHOWONCOMPASS_DELEGATE_BEFORE` and `SHOWONCOMPASS_DELEGATE_AFTER` around the exact saved base `previousShow` call;
  - preserves all base `ShowOnCompass` return values with a pack/unpack wrapper;
  - adds `SHOWONCOMPASS_DELEGATE_ABORT` if the pre-delegation custom cleanup fails;
  - adds `SHOWONCOMPASS_REFUSED` for the non-exact custom action guard;
  - adds `PROMPT_ROUTE_OVERRIDE` for committed explicit Raven prompt writes;
  - adds `PROMPT_BASE_DELEGATE_WITH_INTENT` when a later base prompt query occurs after exact collision ownership has been consumed but a committed Raven prompt intent still exists.
- This commit intentionally changes no routing decision, marker ownership policy, persistence, authority, save state, or progression state.

Instrumentation regression coverage:

- `5ea1478d61c2bef283faf609eaa3d81db183f3aa`
  - synthetic exact Raven -> transient mismatched `currMarkerID` -> prompt disarm -> base `ShowOnCompass` delegation must emit the full before/after boundary and end with the synthetic stock target;
  - a later unoverridden prompt query after a committed Raven action must emit `PROMPT_BASE_DELEGATE_WITH_INTENT`;
  - the latter is only synthetic evidence that the footer can re-enter the base prompt path. It is not yet treated as the field root cause.

No GitHub Actions are configured for these commits. The canonical local v0.10.5 Lua/offline gates must run before the next live reproduction.

Next field proof:

1. refresh the generated All-Ravens delivery proof on `codex/all-ravens-cosmetic-polish`;
2. run the full offline evidence gate and push its result;
3. run `run-raven-native-snapshot-delivery-live-proof-and-push.ps1 -ExpectedBranch codex/all-ravens-cosmetic-polish -CosmeticOnly`;
4. reproduce FIRST Add footer immediacy once;
5. reproduce rapid Add -> Remove -> Add once, deliberately fast enough to trigger the boat regression;
6. type `REGRESSION` if either defect appears so the script rolls back exactly and pushes the full capture;
7. inspect the new routing categories above before making any behavior change.

The specific field question is now deterministic: after `PROMPT_OWNER_MISMATCH`, does the next `SHOWONCOMPASS_DELEGATE_BEFORE` already contain a transient stock/current marker owner, and does `SHOWONCOMPASS_DELEGATE_AFTER` create the boat target? For the footer, does a later `PROMPT_BASE_DELEGATE_WITH_INTENT` occur after the committed Raven footer write?
