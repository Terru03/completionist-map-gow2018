# All Collectibles Production Research Status

## Decision

Static catalogue: **PASS**.

Runtime generation: **BLOCKED, FAIL CLOSED**.

Gameplay test: **NOT RUN**. The exact unloaded, per-instance completion oracle is
not proven for these families. The generated catalogue therefore stays offline;
unknown state must create no marker. No God of War process was launched and no
game, save, or progression file was written.

## Scope and baseline

- Base branch: `codex/all-ravens-release-candidate`
- Base commit: `abbeb1bc6a559336c2d92743e8bb70cd3ae15728`
- Work branch: `codex/all-collectibles-production-research`
- Native inputs: PC WAD records, `mapmaster.dcb`, `quests.dcb`, and decompiled
  Lua state/save code under the local God of War tree.
- Existing 53-entry Raven catalogue, Raven implementation, and Raven tests were
  not changed.

## Static result

| Family | Native result | Tracked target evidence | Status |
|---|---:|---:|---|
| Artefacts | 45 state carriers, 43 physical placements | 9 Ship Head placements vs target 10 | PASS with explicit carrier/placement discrepancy |
| Lore Markers | 40 direct component carriers plus 3 level-script carriers = 43 | target 43 | PASS |
| Legendary Chests | 64 fixed physical objects | 33 map-summary objects vs target 33 | PASS; 31 story/trial extras kept and labelled |
| Nornir Chests | 22 fixed physical parents | 20 joined targets vs target 21 | PASS with one unresolved tracked join |
| Nornir Seals | 30 exact children | 10 Breakable parents x 3 | PASS |
| Nornir Bells | 24 exact children | 8 Bell parents x 3 | PASS |
| Nornir Mechanisms | 12 exact children | 4 MemoryChest parents x 3 | PASS |

Niflheim procedural data is not emitted as fixed markers. The audit records 56
Legendary and 7 Nornir template-placement expansions as excluded procedural
templates. `Lambs Cress` shares the artefact script but has no artefact type and
is explicitly excluded.

Every fixed Nornir parent has exactly three child records. Association comes from
the parent's native Lua-table reference names, then exact object-name lookup in
the same WAD. No nearest-object or distance association is used. Native KeyType
values are only `Breakable`, `Bell`, and `MemoryChest`; catalogue UI families are
Seal, Bell, and Mechanism.

## Identity, location, and grouping

Each row records native object/component identity, exact WAD and SHA-256, record
offsets, full transform chain, world XYZ, realm, region, map-summary quest when
joined, deterministic marker name, and deterministic 64-bit marker UID. Midgard
rows include the solved affine map projection; other realms retain exact world
XYZ and explicit projection metadata.

Prefab definitions can fan out to several placed objects. Extraction expands
every native transform branch, selects exact prefab names where stock child IDs
are shared, and uses outer native composite placement keys. Streamed or alternate
carriers remain distinguishable by native WAD/record identity. Nornir groups use
explicit `parent_catalogue_id` links.

## Exact state evidence

| Family | Exact loaded/checkpoint oracle | Limit |
|---|---|---|
| Artefact | `interact_loot_artifact.lua`: `ACQUIRED = 3`; checkpoint persists `state`; pickup sets `state = ACQUIRED` | No proven read-only unloaded lookup by native instance key |
| Lore Marker | `langcheckruneread.lua`: successful summary update sets `mapSummaryComplete = true`; checkpoint persists/restores it | Three level-script carriers use `bRuneReadStarted` or `wellRead`; no generic unloaded query |
| Legendary Chest | `interact_chest_standard.lua`: `OPENED = 4`; open sets `state = OPENED`; checkpoint persists/restores `state` | No proven read-only unloaded lookup by composite instance key |
| Nornir parent | Actual reward chest uses the same exact `state == OPENED` oracle | `keysUsed` and `challengeComplete` are puzzle progress, not chest-open proof, and are never used to infer completion |
| Breakable seal | Loaded object can prove exact child state through destroyed breakable state or disabled rune visual | Unloaded/pre-install individual seal state is unresolved |
| Bell | Bell ringing/cooldown state is transient | No durable individual completion; child stays tied to exact known-unopened parent |
| Memory mechanism | Current rune/mechanism state is puzzle state | No durable individual completion; child stays tied to exact known-unopened parent |

The local `interact_chest_runic.lua` copy contains old diagnostic additions. This
research uses its native attribute names, checkpoint fields, and direct object
references only. It does not copy the old aggregate inference logic.

## Runtime architecture proof

`collectible_runtime_model.py` is a pure offline oracle, not shipped Lua. It
proves these rules:

- unknown state creates no marker;
- exact collision plus normalized exact UID owns a custom click;
- custom-to-custom and custom-to-stock target replacement works both ways;
- a second click removes only the same target;
- realm and family filters gate visibility;
- Nornir children require an exact known-unopened parent;
- Breakable seals also require exact individual loaded state;
- save change clears all cached state and UI ownership;
- teardown removes UI state, retry is bounded, and no permanent polling exists.

No production Lua or native WAD build was generated because the state gate is
blocked. This is deliberate: static identity and position proof does not justify
showing already-completed collectibles on an existing save.

## Files

- `config/collectibles/v0.10.5/all-collectibles.json`
- `config/collectibles/v0.10.5/all-collectibles.schema.json`
- `tools/v0.10.5/collectible_catalogue.py`
- `tools/v0.10.5/collectible_runtime_model.py`
- `tools/v0.10.5/test_collectible_catalogue.py`
- `tools/v0.10.5/test_collectible_runtime_model.py`
- `docs/research/all-collectibles-native-audit.json`
- `docs/superpowers/plans/2026-09-14-all-collectibles-production-research.md`
- `NEXT_STEPS.md`

## Verification

Focused catalogue tests: 14 passed, including atomic output success and injected
pre-replace failure rollback.

Focused runtime-model tests: 13 passed.

Raven regression tests: 42 passed. Four Lua 5.1 tests skipped because that runtime
is unavailable. Two catalogue generations produced byte-identical SHA-256
`8F86BF3C669258E71EA655C6212320C948E40AD3FC8595F690A7373F8591FCF8`.

The inherited fake-game Raven transaction test could not start because
`archive/all-ravens/all-ravens-release-candidate-offline.json` is absent from the
base checkout. It made no installed-game write. This branch's catalogue output
boundary is covered by the focused atomic-write rollback test instead.

## Gate summary

- Static extraction and schema: **PASS**
- Exact native Nornir parent-child association: **PASS**
- Loaded/checkpoint state semantics: **PASS WITH CHILD LIMITS**
- Exact unloaded/pre-install state: **BLOCKED**
- Safe runtime generation: **BLOCKED**
- Gameplay readiness: **NO**
- Game/save/progression writes: **NONE**
