# Completionist collectible framework

## Decision

Raven stays frozen production. Framework wraps Raven; it does not migrate or
rewrite Raven. Nornir Candidate 3 is first offline consumer. Synthetic probe is
second builder consumer and has no game/runtime claim.

Registry is source of collectible facts. Generic Python owns repeated WAD and
GOPool transforms. Lua marker service owns safe marker state mechanics as an
offline module contract. Lifecycle adapters only publish observed state. They
do not write gameplay state.

## Layers

1. `config/collectibles/v0.10.4/collectibles.json`
   holds stable keys, identities, donor choice, ModelGroup policy, GOPool rows,
   lifecycle adapter, parent relation, filter, and unresolved facts.
2. `tools/v0.10.4/collectible_framework.py`
   loads and validates registry, resolves deterministic test identities, builds
   WAD resource graphs, appends GOPool rows, normalizes, and checks ownership.
3. `tools/v0.10.4/build-nornir-candidate3-offline.py`
   assembles Candidate 3 by selecting `nornir_chest` from registry. Lifecycle
   and native DCB inputs remain pinned historical artifacts.
4. `tools/v0.10.4/completionist-collectible-service.lua`
   defines reusable marker mechanics but is not installed. Frozen Raven Lua is
   golden input, not module consumer.
5. `tools/v0.10.4/run-collectible-framework-offline.ps1`
   blocks active game process, verifies Raven before/after, builds only below
   repository `build/`, runs tests, and writes machine proof.

## Resource recipe

For build-enabled visual types, engine clones proven Raven texture, material,
map model/prototype/root, and HUD model/prototype/root ownership groups. It:

- gives each new payload own name and 16-byte ID;
- gives texture definition and GPU rows own identities;
- binds material only to its two texture definitions;
- binds both models only to collectible material;
- keeps map model link to stock `MG_mapicondock_0`;
- keeps HUD model link to stock `MG_boatdock_0`;
- retargets prototype self ID and model link;
- retargets root prototype ID and loader name;
- clones one parent link for map root;
- applies proven mixed Raven WAD accounting grammar;
- appends declared GOPool map/HUD rows;
- reparses and serializes exactly;
- removes new graph and restores accounting to prove exact source recovery.

Material rule is hard validation, not default guess. `+0x10` must be unique.
`+0x20` must equal donor value `D595197B0961F689`.

## Lifecycle adapters

Adapter types describe state input only:

| Adapter | Known mapping | Completion rule | Hook status |
| --- | --- | --- | --- |
| `killable_collectible` | Odin's Raven | proven Raven completion state | frozen implementation |
| `opened_chest` | Nornir Chest, Legendary Chest | chest `OPENED` | Nornir hook proven offline; Legendary hook unresolved |
| `pickup_collectible` | Artefact | pickup complete | exact hook unresolved |
| `interact_read_collectible` | Lore Marker | read/interact complete | exact hook unresolved |
| `parent_puzzle_collectible` | Nornir Chest | parent reward `OPENED`, not puzzle-only state | proven offline for one target |
| `child_puzzle_element` | Bell, Seal, Mechanism | parent controls suppression | exact child hooks unresolved |

Marker service API separates state from mechanics:

- `RegisterCollectible(definition, adapter)`
- `PublishState(key, instance, state)`
- `ShowMapMarker` / `HideMapMarker`
- `AddCompassTarget` / `ReplaceCompassTarget` / `RemoveCompassTarget`
- `CreateInWorldMarker` / `RemoveInWorldMarker`
- `SetActiveTarget`
- `Complete`

One active target is service invariant. Parent completion suppresses children.
Child state cannot complete parent unless adapter gives an authoritative parent
event. Service contains no save, quest, progression, or marker-state writes.

## Discovery policy

`null` means unknown. Each null required for runtime must have matching entry in
`unresolved`. Deterministic IDs under `synthetic_test` are framework test IDs,
not discovered game IDs. Placeholder types cannot build until needed resource,
native, and lifecycle facts gain evidence.

## Compatibility policy

Raven cannot consume new Lua or Python without new runtime proof, so it stays a
golden fixture. Candidate 3 may use generic resource construction only if exact
WAD SHA, GOPool bytes, normalization, ten-file manifest, and safety facts stay
unchanged. Native and lifecycle generation remain pinned artifacts for this
migration; generalizing them needs separate evidence.

