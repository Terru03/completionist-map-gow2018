# Astra task: v0.10.4 native Completionist map-class registry

## Goal

Resolve the God of War (2018) `WAD_R_UI.GOPool` / `r_ui.wad` map-icon registration model well enough to give the Completionist Raven a stable independent map class without using DockPoint artwork, without globally changing stock classes, and without growing/rebuilding `r_ui.wad` unless the full runtime bookkeeping is understood.

This is a reverse-engineering task. Prefer strong static evidence and small read-only tooling over speculative runtime patching.

## Branch

Work only on:

`feat/v0.10.4-all-ravens`

Start by pulling current origin. Do not rewrite or reset existing history.

## Important current state

The v0.10.3 authored Raven/native navigation baseline is already proven. The Raven has:

- marker name: `Completionist_V103_Veithurgard_Raven_01`
- marker hash: `E15E6BC82AE2773E`
- mapmaster/mapcoords/compassgraph authored records
- native compass navigation proven with `DockPoint`
- map and compass class have been proven independent by changing only the Raven map `Icon` to stock `goMapIconValkyrie_location`; the map rendered a Valkyrie while native compass navigation remained DockPoint.

Do not revisit coordinate/pathing proof.

The map-side problem is registration of an independent custom map icon class.

## Runtime evidence already established

1. `goMapIconValkyrie_location` control proof succeeded with no Dock map proxy.
2. A rebuilt/grown custom `r_ui.wad` + appended GOPool row was unstable. The map partially failed to load and the game crashed. The requested custom Raven resource still instantiated as `mapicondock` in runtime logging. Treat the current grown-WAD builder as offline evidence only, not a safe production route.
3. Existence of a concrete `gomapicon*` final-instance resource in `r_ui.wad` does **not** imply a matching `WAD_R_UI.GOPool` row. `gomapiconcube` and `gomapiconchiseldungeon` were wrongly assumed to be usable donor registrations and both failed because their expected GOPool Name hashes were absent.
4. The stock GOPool contains duplicate Name hashes. The first inventory script incorrectly assumed uniqueness and failed. Commit `9c7c2f7` changes the inventory to preserve duplicate groups and excludes ambiguous duplicate hashes from donor candidates.

## Pinned source hashes

- `r_ui.wad`: `92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04`
- `wad_r_ui.dcb`: `21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a`
- tested v0.10.3 native Raven `mapmaster.dcb`: `1e076f7c5f0aea8d93ad72365bcaa267361503eee10fcdab0522c699b188508a`
- `GoW.exe`: `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`

## First required action

Run and inspect:

`tools/v0.10.4/inspect-r-ui-registered-map-classes.ps1`

It should write:

`archive/field-logs/completionist-v104-registered-r-ui-map-classes.json`

Do not proceed by guessing another donor if the inventory fails. Fix the read-only inventory first.

## Questions to answer

### A. What exactly does GOPool represent?

The root `WAD_R_UI` type is `0x10F`. GOPool is 255 rows, each 16 bytes:

- offset +0: `Name` u64, RTTI attr 0x17C4
- offset +8: `Cnt` u16, RTTI attr 0x17C5
- +10..+15 padding

Determine, using stock data and executable/static references where possible:

1. Why are some GOPool Name hashes duplicated?
2. What does `Cnt` mean in practice?
3. Does a map marker's `Icon` hash resolve directly to a GOPool row, or is there another lookup/translation step?
4. How does a GOPool row resolve to the concrete `gomapicon*` final instance in `r_ui.wad`?
5. Why do some concrete `gomapicon*` WAD resources have no GOPool row?
6. Are there registered GOPool rows that map to resources under names not discoverable by simply hashing `gomapicon*` final instance names?

### B. Find a safe existing registration slot, if one exists

A potential donor must satisfy all of these before any runtime proof:

- matching Name hash really exists in stock GOPool
- mapping from that row to a concrete visual resource is understood
- zero authored `mapmaster` usage
- no known runtime-created/player/system usage
- no GoWLUA references that imply live gameplay use
- not Kratos/player/Omega, no-render, Dock, fast travel, vendor, quest, Valkyrie, or other obviously live stock class
- preferably one unique GOPool row, not an ambiguous duplicate Name hash

Do not classify a donor as safe from `mapmaster` usage alone.

### C. Determine the safest path to a true custom class

Evaluate these separately:

1. **In-place registration rename**: rename one proven-safe GOPool Name hash to `goMapIconCompletionistRaven` while preserving file size and all other bytes.
2. **In-place WAD resource rename/retarget**: if needed, rename/retarget a proven-safe donor final instance/prototype/material chain without growing the WAD and without affecting any stock live users.
3. **Appending a genuinely new GOPool/WAD resource**: only if you can identify and correctly update every runtime-required WAD bookkeeping structure that the previous offline builder missed. Do not assume the existing custom-WAD builder is sufficient.
4. Any alternate native mechanism discovered in `GoW.exe` or DCBs that registers an additional map class without donor hijacking.

Prefer an in-place, size-preserving proof first if technically sound.

## Existing useful evidence/tools

Read these before duplicating work:

- `archive/field-logs/completionist-v104-map-icon-chain.json`
- `archive/field-logs/completionist-v104-r-ui-map-icon-layout.json`
- `archive/field-logs/completionist-v104-r-ui-prefab-inventory.json`
- `archive/field-logs/completionist-v104-raven-ui-visual-clone.json`
- `archive/field-logs/completionist-v104-raven-map-class-control-runtime.txt`
- `archive/field-logs/completionist-v104-raven-direct-visual-runtime.txt`
- `tools/v0.10.4/inspect-r-ui-registered-map-classes.py`
- `tools/v0.10.4/patch-r-ui-gopool-slot.py`
- `tools/v0.10.4/build-raven-ui-logical-clone.py`
- `tools/v0.10.4/build-raven-ui-visual-clone.py`
- `tools/v0.10.3/inspect-native-markers.py`

Known map visual control success log should show `goName=mapiconvalkyrie_location` with `dockProxyUsed=false`.

Known failed custom-WAD runtime log should show requested `goMapIconCompletionistRaven` but `goName=mapicondock`, followed by unstable/partial map loading and crash.

## Raven visual assets already prepared offline

If/when a stable independent map class exists, the project already has a Raven-only visual chain concept and converted textures. Do not spend the task redesigning icons.

Existing reserved logical names include:

- `goMapIconCompletionistRaven`
- `gomapiconcompletionistraven`
- `goProtoMapIconCompletionistRaven`
- `MDL_completionistraven`
- `MAT_AE4AD85BB993F040`
- `TX_completionist_raven_map_diffuse_19A41F00834C19F3`
- `TX_completionist_raven_map_emissive_63F1E18FF93B9037`

The previous grown-WAD packaging of these is **not** assumed runtime-valid.

## Safety constraints

Do not:

- launch the game automatically
- install any candidate into the user's God of War directory unless the task explicitly reaches a strongly validated reversible proof and leaves installation for the user to invoke
- write save/progression state
- call `Map.ChangeMarkerState()` to fake progression
- alter Kratos/Omega/player artwork
- globally replace Dock textures/materials
- mutate legitimate stock Dock marker IDs
- reintroduce direct XYZ/manual-bearing compass navigation
- commit local generated game binaries or copyrighted extracted WAD/DCB payloads

Read-only analysis of the user's local game files is allowed if available in the Codex environment. Generated reports/tools may be committed.

## Deliverables

1. A concise research note under `docs/research/` explaining the actual GOPool/resource mapping and duplicate-row semantics with evidence.
2. Corrected/extended read-only inspector(s) under `tools/v0.10.4/`.
3. A JSON evidence report under `archive/field-logs/` if the environment can run against the user's pinned files.
4. If and only if justified by evidence, a reversible **offline-preparation/runtime-install proof** for one Raven class that does not grow `r_ui.wad` and does not use Dock artwork on the map.
5. Commit and push work to `feat/v0.10.4-all-ravens`.

At the end, state clearly:

- what was proven
- what remains inference
- whether a safe runtime test is ready
- exact command the user should run next, if any

Do not move on to all Ravens or Nornir until one custom Raven map class is stable.
