# Legendary static gate, 2026-09-23

This pass reads shipped game assets and frozen captures only. It does not open
the game, read a live process, install hooks, or write game/save files.

## Four mystery rows

The current branch has already moved the two Tyr rows into its 33 map-counted
candidates. It moved two other physical chests out to keep the native target
total at 33. Those two exclusions are also provisional under a direct-edge
standard. The count reconciliation is useful scope evidence, but its `mapping_basis` assigns
`cal740_leftwing` as the *remaining* Tyr row. The source-level Tyr hints and
target accounting do not contain an exact chest-to-RegionSummary edge.

| WAD | Current catalogue class | Exact state key | Frozen state | Direct map-count edge |
| --- | --- | --- | --- | --- |
| `stn200_lakeext.wad` | unresolved | `0x6596668D5294F4F9` | `4.0` | absent |
| `xpl300_stronghold.wad` | unresolved | `0x59828306F140B0A4` | `4.0` | absent |
| `cal500_runevault.wad` | tracked candidate | `0x3F6E1038E5B9BAEE` | `1.0` | level hint plus target accounting only |
| `cal740_leftwing.wad` | tracked candidate | `0xEEF1DE0863CC4F32` | `2.0` | remaining-row target accounting only |

The first two key and state results come from the same structural identity
rule and frozen staged-carrier decoder used by the accepted 33-row reports.
The gate repeats those exact carrier matches in
`legendary-static-gate.json` on each run.
Both are exact unique GameObject state matches. They do not settle production
class. The native mapmaster has no LegendaryChest summary in either
`Stonemason` or `HuldraStronghold`, but the catalogue assigns those regions by
level namespace. It does not prove the player region at each chest's world
position. The stock `interact_chest_standard.lua` asks
`game.Map.FindPlayerRegion()` when a Legendary Chest opens, then increments
that region's Legendary summary if one exists. A WAD filename is not a static
answer to that call.

Static disassembly of pinned `GoW.exe` SHA-256
`caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`
supports the gap: Lua `FindPlayerRegion` registration points to RVA
`0x9513C0`. That wrapper reads a string from current world context at
`[context+0x4AD0]+0xC50`, applies the case-folded `0x401` hash, and looks up a region
at RVA `0x1EC5D0`. It does not take a chest WAD name or authored chest GUID.
That context string at each chest point has not been established by static
zone/trigger data.

The embedded `xpl300_stronghold` level Lua has
`UI_Event_DiscoverLocation("HuldraStronghold")`; the embedded
`cal500_runevault` Lua has the same call for `TyrsVault`. These are level
discovery hints. They do not bind the chest interaction point to the
`FindPlayerRegion` result. No matching discovery call was found in the
`stn200_lakeext` or `cal740_leftwing` level script records.

Exact searches found each physical GUID only in its own placement override.
Across 561 shipped DCB files, neither physical GUID nor raw placement record
ID had an exact hit. These negative searches narrow the available source wire;
they are not positive proof that either chest is an excluded reward.

## Production candidates

The 33 current candidate rows have 33 distinct derived serialized GameObject
keys. The frozen staged evidence observes an exact state row for 32 of them.
`xpl100_httk.wad` is absent from that capture; its key is derived by the same
rule, but its persisted value is unknown there. `OPENED = 4.0` is proved by
the stock chest script and the accepted state-semantics report.

All 33 parent assignments still need a direct native binding check:

- 31 use `parent_quest_source=unique_region_family_inference`;
- 2 use `parent_quest_source=corrected_map_count_scope_proof`.

Neither source is an exact per-chest RegionSummary wire. The old `PASS_EXACT`
labels in the generated audit attest that target records exist. They should
not be read as proof of chest-to-target ownership. The static gate records
`direct_native_binding_count=0` and keeps Legendary generation off.

## Marker assets

The stock `r_ui.wad` map-icon finals contain no Legendary Chest map class.
The current Steam `mapmaster.dcb` has 382 authored marker rows; its icon names
contain no Legendary Chest class. This does not rule out another native UI
path, but no per-chest native map pin or world marker ID was proved here.
Asset SHA-256: `r_ui.wad` =
`92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04`;
`build/native-source-cache/mapmaster.dcb` =
`aec578e773898a1e60d5ccedd0df08e35b12ab54e4d26f4cd90740948430c2a0`.
Legendary-specific custom map resource, material, texture, compass class,
pool/config ID, and native suppression target still need asset-level proof.
No Raven ID is promoted into a Legendary manifest.

## Gate result

`python tools/v0.10.5/legendary_static_gate.py --output docs/research/legendary-static-gate.json`

Current result: `BLOCKED_FAIL_CLOSED`, 33/33 unique keys, 32/33 observed
staged states, 0/33 direct native bindings, two unresolved rows. No Legendary
runtime candidate should be generated. The next static work is to prove
per-chest region ownership or another direct quest/callback edge, then trace
the actual native icon/marker path and derive separate Legendary assets.
