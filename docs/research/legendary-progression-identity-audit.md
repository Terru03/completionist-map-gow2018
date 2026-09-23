# Legendary Chest native identity and progression audit

## Result

30/33 have an exact native placement key, derived serialized GameObject key, and exact frozen
checkpoint state match. Three current tracked rows have a structural
key but no state observation in the frozen capture.
No per-chest RegionSummary membership or extra event/objective alias was proved.
Runtime delivery stays blocked.

Each physical placement override has a full native state path.
2 catalogue keys differ from
that full path. This audit flags them; it does not alter catalogue data.
The persisted checkpoint lookup uses a different 17-byte serialized
GameObject key: flag 1 + WAD registry hash + object identity hash.
The shared state carrier GUID is not a unique chest key by itself.
All 33 serialized keys are distinct. The frozen capture has 30 exact
state matches for the current tracked set. The older identity snapshot
contains two superseded tracked IDs and omits two current IDs.
Current keys were recomputed and checked against the frozen state report.
The three unobserved WADs are `xpl100_httk.wad`,
`cal500_runevault.wad`, and `cal740_leftwing.wad`.

## Catalogue state-path discrepancy

Two catalogue `physical.state` keys omit the middle GUID
`1a10ffb6-4e57-7e17-2604-f4b11ae71140` that exists in the exact
native placement override path:

| Physical GUID | WAD | Catalogue key | Native state path |
| --- | --- | --- | --- |
| `ace99ef5-472a-bcba-c29b-d2b396a3fdf3` | `xpl980_beachwaterfall.wad` | `ace99ef5-472a-bcba-c29b-d2b396a3fdf3.b36ec130-4042-2d81-123a-9db40831d654` | `ace99ef5-472a-bcba-c29b-d2b396a3fdf3.1a10ffb6-4e57-7e17-2604-f4b11ae71140.b36ec130-4042-2d81-123a-9db40831d654` |
| `d63295f2-44f3-3021-9b00-3c913c0dab69` | `peak720_summitascenthub.wad` | `d63295f2-44f3-3021-9b00-3c913c0dab69.b36ec130-4042-2d81-123a-9db40831d654` | `d63295f2-44f3-3021-9b00-3c913c0dab69.1a10ffb6-4e57-7e17-2604-f4b11ae71140.b36ec130-4042-2d81-123a-9db40831d654` |

The native path and frozen GameObject state both bind these two
physical chests. The catalogue is left unchanged by request.

## Native open path

Pristine `interact_chest_standard.lua` sets `state = states.OPENED` in
`OnOpened`. `OnSaveCheckpoint` returns `{state = state}`; restore reads
the same field. `PutAway` stores a checkpoint when configured, else calls
`game.SubObject.SoftSave(thisObj)` when present. The optional
`onOpenedEvent` callback has no proved per-chest quest/objective alias
in the checked override ASCII. This is a limited negative result.

The same `OnOpened` branch asks `game.Map.FindPlayerRegion()`, then
increments a RegionSummary quest for that active region. The pristine
`questlibrary.lua` starts an inactive quest or increments an active one
by **1**. The 18 quest targets are region aggregate progress goals; their
goals sum to 33, but they do not list physical chest members.
`AwardLoot` uses `RollContainerConditionLoot` for rewards. The checked
scripts do not register a per-chest map marker.

Native sources: `mods/lua_source/gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua`
(`OnOpened` line 366, `state = states.OPENED` line 373,
`FindPlayerRegion` line 381, `OnSaveCheckpoint` line 498);
`mods/lua_source/gameart/scripts/libraries/design/questlibrary.lua`
(`ActivateAndIncrementQuest` line 32, increment lines 37 and 39);
`exec/dc/pc_le/quests.dcb` (per-target offsets in JSON/CSV).

Targeted scans covered 28 source WADs,
561 DCBs, and
493 pristine Lua files. Each full
native state path occurs once in its own placement override.
Known serialized hash/key forms have no extra native source hit.
These
negative hits do not rule out a runtime-only registry or unnamed binary edge.

| WAD | Physical GUID | Serialized object hash | Local state bridge | Region member |
| --- | --- | --- | --- | --- |
| `alf600_templeint.wad` | `040af4fa-440e-f7ba-52f8-e8b317ac3200` | `0x6CE4491007BAF553` | proven frozen | unproved |
| `foot400_arena.wad` | `0a04b4de-469f-3b03-0064-d6827966b213` | `0x09DAEF3A621B6AAF` | proven frozen | unproved |
| `riv475_freyahouseext.wad` | `11e085df-4bd4-7dee-e3a3-448bff9efc62` | `0x4FA6C82A0DC3A612` | proven frozen | unproved |
| `xpl900_islandarch.wad` | `23d3213f-45e3-8b63-2ed8-048e876e472d` | `0xD22F80A99F65461B` | proven frozen | unproved |
| `riv925_freyacave.wad` | `36cb588e-41cb-27a4-6680-52b4529b98a6` | `0x7763E1E104028C98` | proven frozen | unproved |
| `alfdgn110_main.wad` | `48f9e169-4dc7-22a5-49f4-2893d5b79d9f` | `0x8A8E3909F06B56AF` | proven frozen | unproved |
| `xpl980_beachwaterfall.wad` | `50480b3a-40fe-25c4-770f-81a7261cbcb8` | `0x0E3CB0A0F6B3B0F3` | proven frozen | unproved |
| `foot200_mid.wad` | `510bd864-41ac-6a7b-71d4-f59321c2a08f` | `0x9A34E829D84ACDB1` | proven frozen | unproved |
| `xpl920_islandclimb.wad` | `52934398-4fc3-1350-4ac2-0da874d05c01` | `0xFEA864DD25991BFF` | proven frozen | unproved |
| `hel100_calderaheldressing.wad` | `5618d560-4269-40a0-2e5b-39a340c0c209` | `0xC576B2AC18840F89` | proven frozen | unproved |
| `cal100_hub.wad` | `5b424870-484e-691c-e32d-19be71a03059` | `0x5E6478FDEAD88E57` | proven frozen | unproved |
| `xpl850_dungeonforest.wad` | `7a71d104-452e-16e3-9a25-bb8a14e47343` | `0x0F8060BE56D5493B` | proven frozen | unproved |
| `hel100_calderaheldressing.wad` | `8002f429-4486-1752-3d18-9cbd93b23d4b` | `0xD6E4A3EBA27DC106` | proven frozen | unproved |
| `xpl100_httk.wad` | `890a24d2-4d28-64a1-567a-f691c615870f` | `0xF7988EE55AF59F65` | derived only | unproved |
| `riv100_dangersentrance.wad` | `8aabd22a-44df-8f25-a955-fe8e04fc0d95` | `0x8D89C82FB275D258` | proven frozen | unproved |
| `alf370_moatscripting.wad` | `91a9f92a-45d2-d3fd-b922-79b4612ab5d7` | `0x3BB9BCF0D356F66C` | proven frozen | unproved |
| `xpl900_islandarch.wad` | `9226bd44-4f0f-0b95-dbeb-7c927c6b317b` | `0xE4EB2F10110FB462` | proven frozen | unproved |
| `hel300_mainbridge.wad` | `957a57b3-456b-d17f-d247-51a66dbcf01c` | `0x710FCBA234B03512` | proven frozen | unproved |
| `xpl910_islandshipwreck.wad` | `9c0dc602-456a-00fa-44bc-a1a3b599cf67` | `0x6C28D78E448029FC` | proven frozen | unproved |
| `xpl400_huldramines.wad` | `9d7648ab-43bf-99f9-0b0c-bd86b0a998f1` | `0xE702E71E90D53F13` | proven frozen | unproved |
| `peak200_chimneylow.wad` | `9f29650a-4a8a-5d0e-b8bc-43af1dbd3d68` | `0x90E718BD51745309` | proven frozen | unproved |
| `xpl980_beachwaterfall.wad` | `ace99ef5-472a-bcba-c29b-d2b396a3fdf3` | `0x20A263EB545B65EB` | proven frozen | unproved |
| `riv925_freyacave.wad` | `ae9454d5-4e9c-9a23-f219-41b41a4038d3` | `0x099656F362E4C68C` | proven frozen | unproved |
| `alfdgn210_main.wad` | `b97f559c-471f-ab88-50a2-ae8741370020` | `0xB96563BFDCD376BF` | proven frozen | unproved |
| `xpl960_beachship.wad` | `b9e3be9a-46c2-48cc-0ddc-159643259c52` | `0xFE9424CD1136DF1E` | proven frozen | unproved |
| `alf340_trenchbdark.wad` | `c14a0f2b-4559-d859-3478-54bccb307f63` | `0x53BE86560E8CB735` | proven frozen | unproved |
| `cal500_runevault.wad` | `d0b93e27-4754-785e-0823-5285bd6b78f2` | `0x3F6E1038E5B9BAEE` | derived only | unproved |
| `peak720_summitascenthub.wad` | `d63295f2-44f3-3021-9b00-3c913c0dab69` | `0x3978566FB35C5EAD` | proven frozen | unproved |
| `xpl250_funeralinterior.wad` | `d6d6acfe-444f-2ad1-0b49-cea2ba85a1eb` | `0x748BE60F37BAB846` | proven frozen | unproved |
| `xpl910_islandshipwreck.wad` | `d6fb0fd6-4364-453c-c3e3-34a2454e0b75` | `0x8A46240742F96AD3` | proven frozen | unproved |
| `xpl950_beachmaze.wad` | `ede160a5-4530-f55a-7667-f5a39257843c` | `0xEE28511073BA9E35` | proven frozen | unproved |
| `cal740_leftwing.wad` | `f714d2d8-45a3-dd9e-2880-8db4655e757f` | `0xEEF1DE0863CC4F32` | derived only | unproved |
| `peak500_chimneytop.wad` | `ff46dfab-43ef-cfc6-f0f3-82a33e2b571d` | `0x26391CCE7A69F5F9` | proven frozen | unproved |

## Decision

A later Raven-style marker could use the physical placement and exact
checkpoint state only after an unloaded-state read path and Legendary
marker assets are proved. Three keys lack frozen state observations.
No region quest
counter may stand in for per-chest state. No runtime code changed here.
Chest #34 stays separate.

See `legendary-progression-identity-audit.json` for exact file hashes,
record offsets, key hits, and per-row reasons. The CSV has flat rows.
