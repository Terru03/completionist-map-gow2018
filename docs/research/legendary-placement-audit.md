# Legendary Chest placement audit

This is a static placement audit of catalogue rows classified exactly as
`tracked_legendary`. It reads shipped WAD bytes. It gives no runtime permission.

Raw Legendary physical rows: 64. Tracked rows: 33. Verified placements: 33. Unresolved placements: 0.

Excluded from this table: 27 trial rewards, 2 provisional non-map-counted rows, 2 unresolved nontracked rows. See `excluded_raw_rows` in the JSON for exact IDs.

Each row checks the physical GUID and state carrier in native overrides,
the exact transform record path and parent links, source WAD hash,
the recomputed world transform, catalogue progression key, and native audit row.
All 33 use one shared state carrier GUID; physical GUID plus carrier GUID
makes each instance key distinct.

| WAD | Physical GUID | State carrier | World position (x, y, z) | Result |
| --- | --- | --- | --- | --- |
| `alf600_templeint.wad` | `040af4fa-440e-f7ba-52f8-e8b317ac3200` | `b36ec130-4042-2d81-123a-9db40831d654` | `449.326551836818, 0.6959366383590435, 554.9825271786149` | VERIFIED_PLACEMENT |
| `foot400_arena.wad` | `0a04b4de-469f-3b03-0064-d6827966b213` | `b36ec130-4042-2d81-123a-9db40831d654` | `-377.5042724609375, 38.04733657836914, 374.8517150878906` | VERIFIED_PLACEMENT |
| `riv475_freyahouseext.wad` | `11e085df-4bd4-7dee-e3a3-448bff9efc62` | `b36ec130-4042-2d81-123a-9db40831d654` | `-454.25, 59.0, 7.0` | VERIFIED_PLACEMENT |
| `xpl900_islandarch.wad` | `23d3213f-45e3-8b63-2ed8-048e876e472d` | `b36ec130-4042-2d81-123a-9db40831d654` | `35.31472457867079, -25.01800036430359, 306.75586361372115` | VERIFIED_PLACEMENT |
| `riv925_freyacave.wad` | `36cb588e-41cb-27a4-6680-52b4529b98a6` | `b36ec130-4042-2d81-123a-9db40831d654` | `-411.79998779296875, 42.5, 2.25` | VERIFIED_PLACEMENT |
| `alfdgn110_main.wad` | `48f9e169-4dc7-22a5-49f4-2893d5b79d9f` | `b36ec130-4042-2d81-123a-9db40831d654` | `62.930845848712806, 1.4350001999735804, 427.7040412498762` | VERIFIED_PLACEMENT |
| `xpl980_beachwaterfall.wad` | `50480b3a-40fe-25c4-770f-81a7261cbcb8` | `b36ec130-4042-2d81-123a-9db40831d654` | `143.12376021628353, -2.6823670864105225, 382.3302518460225` | VERIFIED_PLACEMENT |
| `foot200_mid.wad` | `510bd864-41ac-6a7b-71d4-f59321c2a08f` | `b36ec130-4042-2d81-123a-9db40831d654` | `-394.4670104980469, 23.17099952697754, 287.92401123046875` | VERIFIED_PLACEMENT |
| `xpl920_islandclimb.wad` | `52934398-4fc3-1350-4ac2-0da874d05c01` | `b36ec130-4042-2d81-123a-9db40831d654` | `237.04469289824766, 0.9680004119873047, -30.207650585440433` | VERIFIED_PLACEMENT |
| `hel100_calderaheldressing.wad` | `5618d560-4269-40a0-2e5b-39a340c0c209` | `b36ec130-4042-2d81-123a-9db40831d654` | `93.84306335449219, 6.0301337242126465, 43.75320053100586` | VERIFIED_PLACEMENT |
| `cal100_hub.wad` | `5b424870-484e-691c-e32d-19be71a03059` | `b36ec130-4042-2d81-123a-9db40831d654` | `-49.42741012573242, -20.521053314208984, -40.00397491455078` | VERIFIED_PLACEMENT |
| `xpl850_dungeonforest.wad` | `7a71d104-452e-16e3-9a25-bb8a14e47343` | `b36ec130-4042-2d81-123a-9db40831d654` | `-58.53902717424626, 8.423837184906006, -642.5077364812828` | VERIFIED_PLACEMENT |
| `hel100_calderaheldressing.wad` | `8002f429-4486-1752-3d18-9cbd93b23d4b` | `b36ec130-4042-2d81-123a-9db40831d654` | `47.28330612182617, -2.951263427734375, 13.04357624053955` | VERIFIED_PLACEMENT |
| `xpl100_httk.wad` | `890a24d2-4d28-64a1-567a-f691c615870f` | `b36ec130-4042-2d81-123a-9db40831d654` | `301.87047576904297, -23.513999938964844, -534.9374084472656` | VERIFIED_PLACEMENT |
| `riv100_dangersentrance.wad` | `8aabd22a-44df-8f25-a955-fe8e04fc0d95` | `b36ec130-4042-2d81-123a-9db40831d654` | `-258.3981628417969, 90.0, -578.4330444335938` | VERIFIED_PLACEMENT |
| `alf370_moatscripting.wad` | `91a9f92a-45d2-d3fd-b922-79b4612ab5d7` | `b36ec130-4042-2d81-123a-9db40831d654` | `403.1204737016655, -14.09075629170195, 496.3911277988473` | VERIFIED_PLACEMENT |
| `xpl900_islandarch.wad` | `9226bd44-4f0f-0b95-dbeb-7c927c6b317b` | `b36ec130-4042-2d81-123a-9db40831d654` | `69.12615446701687, -20.879000425338745, 311.6267362146935` | VERIFIED_PLACEMENT |
| `hel300_mainbridge.wad` | `957a57b3-456b-d17f-d247-51a66dbcf01c` | `b36ec130-4042-2d81-123a-9db40831d654` | `333.7644958496094, 1.0, 50.896034240722656` | VERIFIED_PLACEMENT |
| `xpl910_islandshipwreck.wad` | `9c0dc602-456a-00fa-44bc-a1a3b599cf67` | `b36ec130-4042-2d81-123a-9db40831d654` | `-194.27186131602303, 2.5333447734507217, -246.8355027079403` | VERIFIED_PLACEMENT |
| `xpl400_huldramines.wad` | `9d7648ab-43bf-99f9-0b0c-bd86b0a998f1` | `b36ec130-4042-2d81-123a-9db40831d654` | `-153.41607379913333, -15.803226470947266, 657.2417831420898` | VERIFIED_PLACEMENT |
| `peak200_chimneylow.wad` | `9f29650a-4a8a-5d0e-b8bc-43af1dbd3d68` | `b36ec130-4042-2d81-123a-9db40831d654` | `-356.51129150390625, 140.68141174316406, 793.3782958984375` | VERIFIED_PLACEMENT |
| `xpl980_beachwaterfall.wad` | `ace99ef5-472a-bcba-c29b-d2b396a3fdf3` | `b36ec130-4042-2d81-123a-9db40831d654` | `96.0206266997138, -20.694000244140625, 365.7096838349609` | VERIFIED_PLACEMENT |
| `riv925_freyacave.wad` | `ae9454d5-4e9c-9a23-f219-41b41a4038d3` | `b36ec130-4042-2d81-123a-9db40831d654` | `-399.4270324707031, 46.009830474853516, -37.59158706665039` | VERIFIED_PLACEMENT |
| `alfdgn210_main.wad` | `b97f559c-471f-ab88-50a2-ae8741370020` | `b36ec130-4042-2d81-123a-9db40831d654` | `368.24355861519416, 7.599999690055853, 278.0945959401806` | VERIFIED_PLACEMENT |
| `xpl960_beachship.wad` | `b9e3be9a-46c2-48cc-0ddc-159643259c52` | `b36ec130-4042-2d81-123a-9db40831d654` | `-305.98156696034954, -3.7350006103515625, -313.7171234566855` | VERIFIED_PLACEMENT |
| `alf340_trenchbdark.wad` | `c14a0f2b-4559-d859-3478-54bccb307f63` | `b36ec130-4042-2d81-123a-9db40831d654` | `207.383847970102, -15.509999065995203, 351.0991389790312` | VERIFIED_PLACEMENT |
| `cal500_runevault.wad` | `d0b93e27-4754-785e-0823-5285bd6b78f2` | `b36ec130-4042-2d81-123a-9db40831d654` | `-66.0018539428711, -89.97755432128906, 82.39568328857422` | VERIFIED_PLACEMENT |
| `peak720_summitascenthub.wad` | `d63295f2-44f3-3021-9b00-3c913c0dab69` | `b36ec130-4042-2d81-123a-9db40831d654` | `-463.3553771972656, 1164.8253173828125, 960.8094482421875` | VERIFIED_PLACEMENT |
| `xpl250_funeralinterior.wad` | `d6d6acfe-444f-2ad1-0b49-cea2ba85a1eb` | `b36ec130-4042-2d81-123a-9db40831d654` | `-152.5, 7.5, 705.0` | VERIFIED_PLACEMENT |
| `xpl910_islandshipwreck.wad` | `d6fb0fd6-4364-453c-c3e3-34a2454e0b75` | `b36ec130-4042-2d81-123a-9db40831d654` | `-192.28995898033702, -14.96668517788143, -186.71769804945382` | VERIFIED_PLACEMENT |
| `xpl950_beachmaze.wad` | `ede160a5-4530-f55a-7667-f5a39257843c` | `b36ec130-4042-2d81-123a-9db40831d654` | `-185.1200031483653, -20.280537009239197, 253.38048333398194` | VERIFIED_PLACEMENT |
| `cal740_leftwing.wad` | `f714d2d8-45a3-dd9e-2880-8db4655e757f` | `b36ec130-4042-2d81-123a-9db40831d654` | `8.554201126098633, -41.0285758972168, 10.19240951538086` | VERIFIED_PLACEMENT |
| `peak500_chimneytop.wad` | `ff46dfab-43ef-cfc6-f0f3-82a33e2b571d` | `b36ec130-4042-2d81-123a-9db40831d654` | `-454.8589782714844, 1172.625, 858.6287841796875` | VERIFIED_PLACEMENT |

## Limits

Nearest two tracked positions: 34.410 world units (legendary_chest_23d3213f45e38b632ed8048e876e472d, legendary_chest_9226bd444f0f0b95dbeb7c927c6b317b). No exact duplicate position found.
Nearest excluded physical row is 15.234 world units from a tracked row: `legendary_chest_3c05899e46a619015d4cfb995fb61be0` (non_map_counted_physical). Its class stays outside this table.
World position is native placement data. UI map projection, each chest's
active RegionSummary owner, marker asset readiness, and live visibility
remain unproved. The separate missing 34th identity remains unresolved.
No marker injection, persistence, game file change, or progression write is allowed
by this audit. See `legendary-static-gate.md` for the broader production gate.

Machine files: `legendary-placement-audit.json` has full record offsets and
transform chains; `legendary-placement-table.csv` is the flat placement table.
