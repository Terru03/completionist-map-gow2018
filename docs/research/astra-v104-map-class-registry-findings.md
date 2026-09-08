# v0.10.4 map-class registry findings

2026-09-08, `feat/v0.10.4-all-ravens`. Research pass complete; **custom Raven class
not stable, no safe runtime test ready**. No game launch, install, save access,
or game file write. No all-Ravens or Nornir work.

Evidence: [full report](../../archive/field-logs/completionist-v104-map-class-registry.json),
[pool inventory](../../archive/field-logs/completionist-v104-registered-r-ui-map-classes.json).
Both use task's pinned WAD/DCB/mapmaster. Full report also checks pinned GoW.exe,
stock WAD byte round-trip, nine native code blocks, and 547 Lua files at GoWLUA
commit `1958cf514d56e1278f02570c876ad127462b3551`. Game source hashes match after scan.
Lua report stores paths, line numbers, tokens and hashes; no source payloads.

## A. What GOPool means

**GOPool is a preallocation list, not a resource-name registry or alias table.**
Root `WAD_R_UI` type `0x10F` points at 255 rows at data `0x90`, stride 16.
Each row has `Name:u64` at +0, `Cnt:u16` at +8, six zero padding bytes.
Reader now checks exported root, relative array pointer, count, size and padding.
Old inventory's word `registered` means only "listed in this WAD's GOPool".

1. **Duplicate semantics:** rows 208 (`0xD90`, Cnt 8) and 212 (`0xDD0`, Cnt 2)
   both hash to `74FAAE7497B39361`, `gomainquestworld`. One matching final resource,
   payload 18453. Native pool-add searches by resolved resource pointer and adds
   count to same pool. Thus these rows request 10 instances when both resolve to
   that resource in same scope. They are not two aliases or a spare registration.
   Why author entered two rows is unknown; runtime additive behavior is clear.
2. **Cnt:** requested instance capacity/preallocation. Native setup reads unsigned
   16-bit count, resolves Name, adds capacity and clones that many objects. Checkout
   reads available/allocated/capacity counters; missing pool or exhausted capacity
   can return null. Separate memory estimate multiplies work by Cnt. Count is not
   WAD index, resource ID, marker ordinal, or total authored marker count. Example:
   PrimaryQuest has Cnt 4 but 133 authored records; Dock 40 versus 48 including
   Raven baseline. No live peak or exact lifecycle count measured here.
3. **Icon lookup:** Lua `Map.CreateMarkerIcon` unboxes marker and region, looks up
   native token, reads authored `Icon` string, case-folds/hashes it, then enters
   general resource lookup. That path searches WAD name maps, dependency WADs and
   a global map; resolved resource then goes through pool checkout. No direct
   GOPool-row-index-to-visual step found. Name-only DCB rename cannot define an
   alias to the old resource.
4. **Concrete chain:** all 13 pooled map names hash to matching stock final header
   and payload names. Final's 56-byte name starts +`0x1C`; prototype ID is
   +`0x0C`; parent prototype ID is +`0x54`. IDs match WAD definitions and zero-size
   links. Prototype root node supplies visible GO name (e.g. `MapIconDock`), with
   model/material links in its scope. Report traces each of 21 map-prefixed final
   resources through prototype, parent, child links, model and material. This is
   a stock structural join plus native lookup trace; full loader name-map insertion
   code is not yet traced. Hash match alone does not prove runtime reachability.
5. **Resources with no row:** not all scene objects need a separate pool entry.
   `gomapiconplayer` is found as existing UI object in stock mapmenu line 257 and
   checked in maputil line 29. Quest-area child resources sit under parent icon
   prototypes; mapmenu lines 814–815 finds these children for tracking highlights.
   Three `gomapiconareamainquest_area` finals have distinct parent prototypes:
   AreaMainQuest, ChiselDungeon and AreaEntrance. `gomapicons` is scene hierarchy
   root. Cube and ChiselDungeon remain unpooled; exact runtime use is unproven,
   so neither is declared dead or safe. No pool row means neither meets donor gate.
6. **Names outside map prefix:** 254/255 rows resolve by hashing all WAD names;
   254 unique hashes exist, of which 253 resolve. Most are keyboard/controller
   prompts, compass objects, HUD meters and other UI. Duplicate is compass/world
   quest object, not a map icon. Only row 104, hash `7C4FD1B03EEFC1ED`, Cnt 5,
   has no matching header or final payload name here. It lies among keyboard
   rows; that placement suggests a keyboard resource but is not a name decode.
   Cross-WAD resolution or stale authoring remains possible. No hidden map-class
   alias established; unresolved row cannot meet concrete-mapping donor gate.

Addresses below are RVAs for pinned executable only. Labels are analysis, not
exported symbols. Report verifies selected instructions from each block.

| RVA | Evidence |
| --- | --- |
| `0x951E40` | CreateMarkerIcon wrapper; lookup call `0x951E8D`, create call `0x951E9A` |
| `0x903F40` | Token Icon string at +8, folded hash loop, call `0x750920` |
| `0x750920` | Name maps, dependency search, resource resolution, pool checkout `0x60EDA0` |
| `0x672A00` | GOPool Name/Cnt loop; row stride 16; call `0x60DD80` |
| `0x60DD80` | Resource-pointer equality; capacity add at `0x60DE6B`; Cnt clone loop |
| `0x60D8B0` | Pool search by resource pointer, then dependency pools |
| `0x60EDA0` | Available/capacity checks; null return when no usable pool |
| `0x673FE0` | Incremental warmup visits every row Cnt times |
| `0x5B813D` | Count multiplies memory/work estimate |

## B. Donor result

**No safe donor established.** All 13 pooled map classes have authored use:

| Class suffix | Cnt | Authored use |
| --- | ---: | ---: |
| PrimaryQuest | 4 | 133 |
| SecondaryQuest | 36 | 47 |
| AreaMainQuest | 4 | 16 |
| AreaSideQuest | 20 | 20 |
| FastTravel_Finale | 2 | 1 |
| FastTravel | 42 | 45 |
| FastTravel_Alt | 2 | 1 |
| AreaEntrance | 18 | 15 |
| Vendor | 17 | 17 |
| Fight_location | 23 | 23 |
| Dock | 40 | 48 |
| Valkyrie_location | 9 | 9 |
| NoRender | 20 | 8 |

Other pool rows are not spare merely because mapmaster has no use. Their UI,
input, compass and HUD roles need preservation. Exact-token Lua scan includes
full GO names and names without `go`; dynamic names and native-only callers can
escape it. No text hit is never a safety proof. Unresolved row 104 and duplicate
MainQuestWorld fail donor gates. No global Dock, player, Valkyrie or quest swap.

## C. Four routes and old builder defects

| Route | Decision |
| --- | --- |
| In-place GOPool Name rename | Reject now: no safe donor; Name resolves resource, not old row artwork. |
| In-place WAD rename/retarget | No proof built: needs unused resource and all names/IDs/scopes/material users mapped; no qualifying donor. |
| Append new GOPool/WAD resource | Not runtime-ready: concrete defects below, plus full heap/name-map bookkeeping unresolved. |
| Alternate native registration | Pool-add exists, but needs resolved resource and WAD lifetime context. No safe public extra-class API established. |

**Two new static defects found in existing grown candidates:**

- Raven final header says `gomapiconcompletionistraven`; its payload name at
  +`0x1C` still says `gomapicondock`. Both logical and visual candidate show this.
  Stock finals have matching header and payload names. Retained prototype node
  name also means `goName=mapicondock` alone cannot distinguish fallback from a
  clone that retained that node name. Do not claim this log proves either cause.
- Builder confuses file payload index with WAD runtime type-table range. Dock
  file payload index 13914 falls numerically in table range `0xD`; Dock's actual
  payload type word is `0x20001`. PrimaryQuest index 13753 falls in `0x2000C` but
  has same actual type `0x20001`. Stock rig counts by payload type word match
  table exactly: `0x10001=1724`, `0x20001=2072`, `0x30001=586`, `0x40001=1`.
  Logical candidate contains 2073 finals but declares 2072. Visual candidate has
  1725 prototypes but declares 1724, and 2073 finals but declares 2076. Correct
  total and byte reparse did not catch wrong per-type allocations.

These defects invalidate prior structural "safe" claims. They do not prove exact
crash cause, nor prove that fixing only these fields repairs runtime. Old builders
remain historical offline evidence, now marked as such. No replacement builder,
installer or candidate created. Task permits append only after **every** required
runtime bookkeeping structure is understood; that gate remains unmet.

One possible later route is use of an already present unpooled resource with new
pool capacity. That avoids WAD growth but still needs full use/lifetime proof and
DCB memory budgeting. Cube/Chisel absence from mapmaster is insufficient. Native
pool-add could also be reached by future plugin work, but no calling contract,
resource registration, threading or lifetime proof prepared here.

## Reproduce; next action

From repo root, repeat read-only full scan with local pinned Lua checkout and
existing Capstone under ignored `dist/`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\v0.10.4\inspect-map-class-registry.ps1
```

Wrapper checks branch and writes JSON only. It reads existing offline candidates
if present. `-LuaRoot` and `-PythonModuleDir` accept other existing local paths;
it installs/downloads nothing. Lua checkout must be clean at pinned commit.
Direct Python CLI exposes same scan and optional `--candidate-wad` arguments.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\v0.10.4\inspect-r-ui-registered-map-classes.ps1 -NoPublish
python .\tools\v0.10.4\test_map_class_registry.py
```

Next engineering gate: trace WAD type-specific allocation/name-map construction
and budget fields, or establish a truly unused existing resource. No install
command appropriate now. Do not retest old grown WAD. Runtime acceptance remains
pending, not passed. Source pins and static facts proven; full loader bookkeeping,
author intent behind duplicate rows, unresolved row 104, dynamic use and crash
cause remain unknown.
