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
