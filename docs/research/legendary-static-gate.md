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

Further disassembly of the same pinned executable shows context-pointer
lifecycle, but does not yet identify the active context at a chest point. The constructor at
RVA `0x73C400` clears object offset `+0x4AD0` at `0x73C441`. RVA `0x733FF0`
can set `+0x4AD0` at `0x7341A5`; RVA `0x738F70` clears it at `0x738FCE`
when its selected object is removed. Separate instructions at `0x73C728`
and `0x730ECF` write a **pointer value** at a `+0xC50` offset on a related
object. They cannot be equated with the wrapper's `+0xC50`, which it reads
as **inline bytes**. Those pointer writes do not identify its string source.
No `+0x470` to region-name source claim follows from those writes.
The active object, its authored region/zone record, and its geometry at each
chest point remain unproved. The gate records zero direct bindings.

Other static callers treat the same `+0x4AD0` pointer's inline `+0xC50`
bytes as a level/area name: RVA `0x48F750` compares them with
`Stn200_LakeExt`, `0x48D2B4` with `Xpl300_Stronghold`, and `0x48D261`
with `Cal500_RuneVault`. RVA `0x487689` compares them with the shorter
`for200` code. These are literal comparisons in the pinned executable.
They help identify the field's meaning, but do not tell which context object
is selected when any chest opens. They are not chest-to-region bindings.

RVA `0x4B7A76` in the constructor at `0x4B7400` addresses its inline
`+0xC50` buffer. At `0x4B7A83`–`0x4B7A93`, it copies 32 bytes from shared
buffer RVA `0x1239120` with imported `strncpy`, then writes a terminator at
`+0xC6F`. The shared buffer has static write sites: `0x41F510` clears its
first byte, `0x42108C` copies from a caller-supplied pointer, and
`0x6751AE`, `0x675829`, `0x675E43`, `0x676343` also copy into it. This
identifies an initialization data path for a `+0xC50` field, but the source
buffer's relation to authored zone geometry, and the exact type relation to
`FindPlayerRegion`'s selected object, remain unproved. No chest binding
follows from these copies.

The `0x421040` buffer writer has static callers that pass resource names:
RVA `0x404C2D` passes literal `R_System`, and `0x67C94B` passes literal
`R_Perm`. Another caller at `0x676932` passes a name at its object's
`+0x84`. Thus this shared buffer is used for resource/WAD names, which fits
the literal level-name comparisons above. It does not identify the selected
resource at a Legendary Chest's point, or prove that resource name equals a
RegionSummary owner. The context selection and spatial join are still open.

Another `+0x4AD0` writer at RVA `0x73B7C0` narrows the selection path.
At `0x73B7F0`–`0x73B80D` it scans up to `0x40` global slots with stride
`0xEE28`, compares the caller's integer to a slot object's `+0xC3C`, then
copies that slot's `+0xEE20` pointer into the context's `+0x4AD0` at
`0x73B82D`. The global slot bases resolve to RVAs `0x282B030` and
`0x281C210`. This proves a runtime slot-selection step. It does not yet
identify the authored zone record, the selected slot for a chest point, or
the slot's spatial bounds. Those remain the next static trace targets.

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

The gate JSON now includes `ownership_proof_rows`: one audit row for each of
the 33 candidates plus `stn200_lakeext` and `xpl300_stronghold`. Each row has
WAD, physical GUID, placement record, world point, derived serialized key,
proposed RegionSummary target, source offset, and proof strength. `region_name`
is null for all 35 because none has a direct chest-to-active-region edge;
`proposed_region_name` preserves the earlier catalogue guess separately.
This table is a work list, not a production allowlist. It covers all four
mystery WADs because `cal500_runevault` and `cal740_leftwing` are among the
33 candidates.

## Marker assets

The stock `r_ui.wad` map-icon finals contain no Legendary Chest map class.
The current Steam `mapmaster.dcb` has 382 authored marker rows; its icon names
contain no Legendary Chest class. This does not rule out another native UI
path, but no per-chest native map pin or world marker ID was proved here.
Asset SHA-256: `r_ui.wad` =
`92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04`;
`build/native-source-cache/mapmaster.dcb` =
`aec578e773898a1e60d5ccedd0df08e35b12ab54e4d26f4cd90740948430c2a0`.
Parsing shipped `r_ui.wad` yields 53,777 records and 119 distinct record
names containing `mapicon`; none names a Legendary Chest. This is still
negative class-name evidence, not proof that no dynamic marker exists.
The extracted `interact_chest_standard.lua` (SHA-256
`943021f321c708561e62d4c9b6926c01b3c131c2057fbed7e4c136dbed707bdc`)
has no `marker`, `icon`, or `compass` API text. Its Legendary open path calls
`FindPlayerRegion` and increments the resulting RegionSummary, with explicit
branches for `TyrsVault` and `TheHallofTyr`. This is a negative check of one
interaction script, not proof that no other native presentation path exists.
Legendary-specific custom map resource, material, texture, compass class,
pool/config ID, and native suppression target still need asset-level proof.
No Raven ID is promoted into a Legendary manifest.

`tools/v0.10.5/audit-legendary-marker-assets.py` now repeats the two pinned
asset scans and archives all 13 authored map icon class counts and 119 UI
`mapicon` record names in `legendary-native-marker-assets.json`. It verifies
Steam build 11168363's 74,128-byte mapmaster hash before parsing. No
`Legendary` or `Chest` class name appears in either asset. The static gate
consumes this report, keeps native marker coverage and custom resource
readiness false, and rejects any report that claims runtime permission. The
result remains a class-name negative check, not proof of full native marker
absence or a usable custom asset path.

## Gate result

`python tools/v0.10.5/legendary_static_gate.py --output docs/research/legendary-static-gate.json`

Current result: `BLOCKED_FAIL_CLOSED`, 33/33 unique keys, 32/33 observed
staged states, 0/33 direct native bindings, two unresolved rows. No Legendary
runtime candidate should be generated. The next static work is to prove
per-chest region ownership or another direct quest/callback edge, then trace
the actual native icon/marker path and derive separate Legendary assets.

The gate records both checkout-byte `source_sha256` and LF-normalized
`source_lf_sha256`. Windows CRLF checkout hashes differ from pinned Git blob
hashes even when evidence content is identical. This second digest permits
exact comparison with exported branch files without weakening any gate.
