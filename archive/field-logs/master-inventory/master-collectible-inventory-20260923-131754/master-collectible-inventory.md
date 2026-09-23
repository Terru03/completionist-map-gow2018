# Master collectible inventory

Generated: `2026-09-23T10:17:59.738784+00:00`

Native game/repository evidence is authoritative. Guide counts are audit-only. Runtime marker generation is disabled by this report.

## Family audit

| Family | External guide | Physical | Native target | Tracked candidates | Explained untracked | Unresolved | Production ready | Audit status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Odin's Raven | 51 | 53 | 51 |  | 0 | 2 | 0 | GUIDE_MATCHES_NATIVE_ACCOUNTING_TARGET_MEMBERSHIP_UNRESOLVED |
| Artefact | 45 | 45 |  |  | 0 | 36 | 0 | ACCOUNTING_EVIDENCE_MISSING |
| Nornir Chest | 21 | 22 |  | 21 | 1 | 0 | 0 | GUIDE_MATCHES_TRACKED_CANDIDATES |
| Legendary Chest | 34 | 64 |  | 33 | 29 | 2 | 0 | GUIDE_TRACKED_CANDIDATE_DISAGREEMENT |
| Lore Marker | 39 | 43 | 43 |  | 0 | 3 | 0 | GUIDE_NATIVE_TARGET_DISAGREEMENT |
| Realm Tear Encounter | 18 | 0 | 19 |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| Jotnar Shrine | 11 | 0 | 11 |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| Purple Language Cipher Chest | 13 | 0 | 8 |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| Treasure Map | 12 | 0 |  |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| Treasure Dig Spot | 12 | 0 |  |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| Hidden Chamber | 7 | 0 |  |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| Valkyrie | 8 | 0 |  |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| Valkyrie Queen | 1 | 0 |  |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| Mystic Gateway | 38 | 0 |  |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| Shop | 16 | 0 |  |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| Dragon | 3 | 0 |  |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| Favor | 15 | 0 |  |  | 0 | 0 | 0 | NO_PHYSICAL_EVIDENCE |
| nornir_bell |  | 24 |  |  | 0 | 0 | 0 | UNPOLICIED_NATIVE_FAMILY |
| nornir_mechanism |  | 12 |  |  | 0 | 0 | 0 | UNPOLICIED_NATIVE_FAMILY |
| nornir_seal |  | 30 |  |  | 0 | 0 | 0 | UNPOLICIED_NATIVE_FAMILY |

Raven native audit narrows two surplus objects to CalderaShores (2 physical / 1 target) and Riverpass (7 / 6). It does not name the two specific objects outside Labor accounting.

Legendary tracked candidates are not a production allowlist. The external guide expects 34; native candidates remain 33.

Artefacts have 45 physical objects. Nine Ship Heads have direct parent attributes against a target of ten. The other 36 lack proved RegionSummary ownership; guide count 45 does not settle accounting.

Lore has 43 physical objects and a native Summary target of 43, versus external guide count 39. Forty object overrides hold direct parent names. Three level Lua callback clues lack exact callback-to-object links. No row was dropped to match a guide count.

Realm Tear research gate pins 19 native PocketRift Summary targets and 14 direct callback carriers. Physical encounter census is unproved, so master has no Realm Tear row yet.

Jotnar Shrine research gate pins native Triptych objective 11 and 13 distinct named placements. Exact per-object membership and exhaustive physical census remain open, so master has no Jotnar Shrine row yet.

Cipher Chest research gate pins two native four-piece language quests and no direct per-chest cipher item record. Physical chest census is unproved, so master has no Cipher Chest row yet.

- Artefact gate catalogue hash `1a9b869711c66bfbf6d2b574571d6d1451e256eb2f58964f8a83f1dd28e06142` is for Windows CRLF checkout bytes. Pinned Git blob hash is `3cff46488530ac642fb07a7d666f6196913fcd72f774226a899f651bb3facebe`; normalized contents match.
- Nornir Chest gate catalogue hash `df4a44914426599a52ab28bf165142941f950f407b9919b6519ee65968b51ae7` is for Windows CRLF checkout bytes. Pinned Git blob hash is `15e4713ed36d56bfea01ec33aeb94f449ecbe2efc78e4ae7dbe52e9f36b402ba`; normalized contents match.
- Legendary Chest gate catalogue hash `27e2c1dc79a8ae2ebee07ac39647943829ad76b3c5110250f4b90dfe4b2d55d9` is for Windows CRLF checkout bytes. Pinned Git blob hash is `067da61017d362f20a38ec7908facf4af8abefcdc29cf7f82aad7aaf89d4d3b4`; normalized contents match.
- Lore Marker gate catalogue hash `21ff36fea434590f13c1211caa02721b8b5138ec12486f23e9e60d639dd8617a` is for Windows CRLF checkout bytes. Pinned Git blob hash is `6983e758803692bf48c893da752258603679169323737bb7ff2fc8a0e75b011f`; normalized contents match.

## Hard marker rules

- Never generate a marker from guide data alone.
- Never duplicate an adequate native in-game marker.
- Never turn procedural/repeatable/template placements into fixed markers.
- A guide/native count disagreement remains fail-closed until explained by positive native evidence.
- A physical row and a quest/accounting target are separate concepts; do not invent physical rows to satisfy counters.

## Pinned evidence

- `codex/collectible-ship-heads@36bf3438b5453b556ddcbb45637a6c6b939d3252` `config/collectibles/v0.10.5/all-collectibles.json` SHA-256 `15e4713ed36d56bfea01ec33aeb94f449ecbe2efc78e4ae7dbe52e9f36b402ba` (seed_catalogue)
- `codex/all-ravens-release-candidate@f665f61935e1723c2b68d1e162cbde228e7de89b` `catalogue/odins-ravens.json` SHA-256 `26cb613a5e8da6efb036b245fe106aed1ad205d4cfc5271398448819b32e5d56` (family_catalogue)
- `codex/all-ravens-release-candidate@f665f61935e1723c2b68d1e162cbde228e7de89b` `archive/all-ravens/native-raven-catalogue-audit.json` SHA-256 `0c53e6727d1df5bc15bf428cf4c126be12142015d9935239782e0debaa8d4f1a` (family_audit)
- `codex/collectible-nornir-chests@37f19b164bf370578ed058274d5020c2d5ab02ad` `config/collectibles/v0.10.5/all-collectibles.json` SHA-256 `15e4713ed36d56bfea01ec33aeb94f449ecbe2efc78e4ae7dbe52e9f36b402ba` (family_catalogue)
- `codex/collectible-nornir-chests@37f19b164bf370578ed058274d5020c2d5ab02ad` `docs/research/nornir-static-gate.json` SHA-256 `945d5526cc8239b65aa29e8f6a35221092f957ec2c480ac87328e301f13eeb20` (family_gate)
- `codex/collectible-legendary-chests@e14bef3f09f17f3f10f2e12b95640d7417b8cdc5` `config/collectibles/v0.10.5/all-collectibles.json` SHA-256 `067da61017d362f20a38ec7908facf4af8abefcdc29cf7f82aad7aaf89d4d3b4` (family_catalogue)
- `codex/collectible-legendary-chests@e14bef3f09f17f3f10f2e12b95640d7417b8cdc5` `docs/research/legendary-static-gate.json` SHA-256 `f31c8f24bdeb5ecec8736b1a187e1a2018192767013758d53f1154c10f33f7cb` (family_gate)
- `codex/collectible-artefacts@061f5131a11ab7d61c24900e3a1324d1c899602e` `config/collectibles/v0.10.5/all-collectibles.json` SHA-256 `3cff46488530ac642fb07a7d666f6196913fcd72f774226a899f651bb3facebe` (family_catalogue)
- `codex/collectible-artefacts@061f5131a11ab7d61c24900e3a1324d1c899602e` `docs/research/artefact-static-gate.json` SHA-256 `b6a631043e4052ced022f8c10c8fc74f80ba44ea7270e6a1fb00d30fa63417e8` (family_gate)
- `codex/collectible-lore-markers@740e06afe90cee7839919d806eed8c17647e3970` `config/collectibles/v0.10.5/all-collectibles.json` SHA-256 `6983e758803692bf48c893da752258603679169323737bb7ff2fc8a0e75b011f` (family_catalogue)
- `codex/collectible-lore-markers@740e06afe90cee7839919d806eed8c17647e3970` `docs/research/lore-static-gate.json` SHA-256 `cae84e490a5ce4bfc3445d2f40b91ad0eb4fda8c73a04fd841924ca38afa86a8` (family_gate)
- `codex/collectible-realm-tears@4dbecd9b6c5939810608a6b4401965ca771ff6d8` `docs/research/realm-tear-static-gate.json` SHA-256 `ed35b26c9402129a3cf7ef9bf4812040c4a34515f7728bbf6d35718600c128e3` (research_gate)
- `codex/collectible-jotnar-shrines@3f2b215eb04618619afa53dc1bf8b1a127fb3698` `docs/research/jotnar-shrine-static-gate.json` SHA-256 `f54d3365a188cb3d9c9daa6ad10b31a87c16a9fef031da5fd5a9c9bbb35b0603` (research_gate)
- `codex/collectible-cipher-chests@472a8ce20b08286689e48a4fb65fc7c23c120fff` `docs/research/cipher-chest-static-gate.json` SHA-256 `9cbd200eaf73dcd0d310bd6380c9179e83f660bbb0e64665ffd574a7d1b707e7` (research_gate)

## Inventory rows

| Family | Subtype | Realm | Region | WAD | Physical ID | Tracking class | Production |
|---|---|---|---|---|---|---|---|
| artefact | Alfheim | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf340_trenchbdark.wad | 0d530408-4995-7335-c6db-68809206f5d1 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Alfheim | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alfdgn110_main.wad | 48edaa8b-407e-24be-d474-bebea8ea3821 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Alfheim | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf345_trenchbdarktwr.wad | 56c4354a-4141-de7a-fc7f-2e8447ab8767 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Alfheim | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf370_moatscripting.wad | 5bf15dbc-4861-3f5b-548f-d2a673d8f7bc | accounting_unresolved | blocked_accounting_and_state |
| artefact | Alfheim | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alfdgn210_main.wad | 6e3739ea-4ac8-107c-495a-61af774a9b03 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Alfheim | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf325_trenchadarktwr.wad | 707ae0e2-4dc7-bc9a-56c1-9eb7ce17b351 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Ship Head | 7CE593BC21393690 | 018E0CE2EAEAA53D | xpl940_beachcave.wad | 7d8a35dc-4d6a-abf8-065e-1ead0c470fcc | shiphead_direct_parent | blocked_shiphead_target_and_state |
| artefact | Ship Head | 7CE593BC21393690 | 018E325B7D1CFC3B | xpl950_beachmaze.wad | 5bb11ed5-419b-42ca-ba81-3598d29ca473 | shiphead_direct_parent | blocked_shiphead_target_and_state |
| artefact | Ship Head | 7CE593BC21393690 | 2FDD4E80C774CB0E | xpl910_islandshipwreck.wad | fda83783-4b36-1579-d4a2-9194810c3d09 | shiphead_direct_parent | blocked_shiphead_target_and_state |
| artefact | Ship Head | 7CE593BC21393690 | 3A9BFC89F5AB6FE3 | xpl970_beachtower.wad | 01a8ba24-409b-5fb4-9a1c-18b43669fe44 | shiphead_direct_parent | blocked_shiphead_target_and_state |
| artefact | Mask | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv200_dangersmain.wad | 0a43e495-4d4f-ff46-abb9-ca8e34d875c0 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Mask | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv325_dangersexit.wad | 0da7cb97-44da-59cb-80fe-319d95cada55 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Mask | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv475_freyahouseext.wad | 28b7fe13-49cd-c49d-a573-c6a0657f0a9d | accounting_unresolved | blocked_accounting_and_state |
| artefact | Mask | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv430_forestboartrack.wad | 468c195b-4808-89e3-5474-2b876aef3a11 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Mask | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv400_forestintro.wad | 6fa420df-406b-e3d0-33b7-eea35a4d10fe | accounting_unresolved | blocked_accounting_and_state |
| artefact | Mask | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv200_dangersmain.wad | 85c29c2b-4203-0656-4c28-b5b09e22532c | accounting_unresolved | blocked_accounting_and_state |
| artefact | Mask | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv475_freyahouseext.wad | cf7627ad-4867-11d9-eab3-339782e5a147 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Mask | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv925_freyacave.wad | fa511e0a-4224-21b7-acc0-1fa5829c4fe3 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Ship Head | 7CE593BC21393690 | 6732D984CAA9285A | xpl980_beachwaterfall.wad | 379728fc-47e4-a966-be1f-c9926011184b | shiphead_direct_parent | blocked_shiphead_target_and_state |
| artefact | Ship Head | 7CE593BC21393690 | 6732D984CAA9285A | xpl980_beachwaterfall.wad | 6cffc988-4efa-77b4-24ba-f987adfdba6a | shiphead_direct_parent | blocked_shiphead_target_and_state |
| artefact | Toy | 7CE593BC21393690 | 7AF9D3D169EFE9B7 | for650_bridge.wad | 8916f55c-4511-b74b-a860-1ba7ef3d86bb | accounting_unresolved | blocked_accounting_and_state |
| artefact | Toy | 7CE593BC21393690 | 7AF9D3D169EFE9B7 | for400_intersection.wad | a0588a94-42f0-118b-dce0-cda751b8605d | accounting_unresolved | blocked_accounting_and_state |
| artefact | Toy | 7CE593BC21393690 | 7AF9D3D169EFE9B7 | for560_wolfpit.wad | ab662cc1-4c4a-2132-7111-dea1a34b96c3 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Ship Head | 7CE593BC21393690 | 7B7F0B522FFA9124 | cal100_hub.wad | 4a3d3149-42f1-87f6-9ee5-b78302e118fe | shiphead_direct_parent | blocked_shiphead_target_and_state |
| artefact | Toy | 7CE593BC21393690 | 7B7F0B522FFA9124 | for200_house.wad | 989065ff-4bde-64f5-ec95-7da2759037cb | accounting_unresolved | blocked_accounting_and_state |
| artefact | Ship Head | 7CE593BC21393690 | 7B7F0B522FFA9124 | xpl960_beachship.wad | bd9a46a3-4b8f-d466-0be2-129e27fa4004 | shiphead_direct_parent | blocked_shiphead_target_and_state |
| artefact | Mask | 7CE593BC21393690 | 7B7F0B522FFA9124 | riv350_calderavista.wad | c9b7e230-40c2-1e2d-a5fe-8ba4be8ad415 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Ship Head | 7CE593BC21393690 | 7B7F0B522FFA9124 | cal100_hub.wad | f7fbfc3f-4499-1b3d-a378-71879e6de737 | shiphead_direct_parent | blocked_shiphead_target_and_state |
| artefact | Horn | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | xpl200_funeral.wad:2768cb29f445634bb075f7a858cabcc3 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Horn | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | xpl200_funeral.wad:52e9ebf8ef1b3343b5d025a73ad6fa91 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Horn | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | xpl200_funeral.wad:b6e2b2a41a1b3e4c9ff1f8e5f877039a | accounting_unresolved | blocked_accounting_and_state |
| artefact | Horn | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | xpl200_funeral.wad:bb9465a7407c9849bf891e0205dac801 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Horn | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl250_funeralinterior.wad | xpl250_funeralinterior.wad:3f176e49e0a0cd4f8cf59ada5fe9c2d8 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Horn | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl250_funeralinterior.wad | xpl250_funeralinterior.wad:4813767722fa414b9a3d4972dc8874e7 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Cup | 7CE593BC21393690 | ED623FA0A76B2934 | peak210_rollerroomlh.wad | 33f59ee7-46f6-3f40-199e-5f90cad3c236 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Cup | 7CE593BC21393690 | ED623FA0A76B2934 | peak200_chimneylow.wad | 6f83c0ef-48ed-a412-0501-35a827d51a7a | accounting_unresolved | blocked_accounting_and_state |
| artefact | Cup | 7CE593BC21393690 | ED623FA0A76B2934 | peak740_summitpeak.wad | b1879436-4cc6-b6a5-c085-96ab8699f35b | accounting_unresolved | blocked_accounting_and_state |
| artefact | Cup | 7CE593BC21393690 | ED623FA0A76B2934 | peak720_summitascenthub.wad | b52df625-45c1-6741-e6f2-278f9e2ccc32 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Cup | 7CE593BC21393690 | ED623FA0A76B2934 | peak780_summitexit.wad | f5bd8953-457f-9662-d074-d798a111abfc | accounting_unresolved | blocked_accounting_and_state |
| artefact | Cup | 7CE593BC21393690 | ED623FA0A76B2934 | peak140_caverndark.wad | fae85e59-4ef7-9ee2-e204-719767dd5287 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Brooch | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel350_chiselarena.wad | c7f91ac1-447c-ff68-5996-96bbbb58e7b7 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Brooch | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel100_calderaheldressing.wad | eb672a16-47b1-f7e6-4595-e48f821670f5 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Brooch | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel300_mainbridge.wad | hel300_mainbridge.wad:00c124ebae0bc24f8b64cc6305246b22 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Brooch | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel300_mainbridge.wad | hel300_mainbridge.wad:b5b33ffb0d723f44a135047d5a839e32 | accounting_unresolved | blocked_accounting_and_state |
| artefact | Brooch | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel300_mainbridge.wad | hel300_mainbridge.wad:e4b6326ae64d514490a45593d471478f | accounting_unresolved | blocked_accounting_and_state |
| legendary_chest | Legendary | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf600_templeint.wad | 040af4fa-440e-f7ba-52f8-e8b317ac3200 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alfdgn110_main.wad | 48f9e169-4dc7-22a5-49f4-2893d5b79d9f | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf370_moatscripting.wad | 91a9f92a-45d2-d3fd-b922-79b4612ab5d7 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alfdgn210_main.wad | b97f559c-471f-ab88-50a2-ae8741370020 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf340_trenchbdark.wad | c14a0f2b-4559-d859-3478-54bccb307f63 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 0656339a-4c04-a369-8b80-c0ae57ed2e24 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 0e87c24a-4063-2a8e-0649-68874d2b33fc | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 0f68bc8d-434f-c653-dd11-9d88fe25ac39 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 1426a756-4686-9538-a1aa-b6834be04997 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 167c0b9e-4424-95b3-7cbb-e6b0a59421c9 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 1ea4b3d2-4aaa-e300-1a7c-779588579d23 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 2106ba90-4751-00c6-a58e-a0ac3e44f84b | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 3398a597-42fb-97a1-ffa9-0a999575ad86 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 3a43afc4-48ef-450e-8db6-478342603b96 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 4e9ceb39-46ff-c7ee-27f9-4a8421e26426 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 5ee9b999-4916-8a00-3242-f99b3a7a9e40 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 62733a59-4d3d-75ea-fab5-7d8f356c5e5d | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 778c6680-4cd4-9dc1-154a-6e87d91b6f94 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 7e85dc2d-4905-c3d5-3d06-388e05fa3a3d | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 8666ad60-4564-72e7-c467-8183988ff6a6 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 86a82b8b-451b-29c7-671e-ce9c0c3b02b6 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 8751f6cc-4bc7-6143-fafe-0fbbd24835e7 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 986af1ac-43ce-9297-1070-738ef0f0e26f | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | 9af2b519-4b2e-6476-34c4-a89eebf594cd | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | a727239b-4ba2-7f22-bd1f-34bef81b9c26 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | a7fa046d-4390-121f-ef12-309f326e5a73 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | a9e88e5d-4159-d86d-6bbd-af98ea1421ef | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | af802a02-4b7e-bfbf-480f-449f9c033616 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | b7e0c5d1-4e1c-f09b-6140-10bbc6cacf16 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | d389c191-4016-7b88-d7a6-819e7c392c93 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | d3cc7462-4839-fc65-7d7e-cd8f255e0113 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 64F56AEB8C58F771 | 64F56AEB8C58F771 | msp100_base.wad | ed7fec9d-4108-85a9-729d-c3baab012f1f | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 7CE593BC21393690 | 0000489975E7755D | xpl100_httk.wad | 890a24d2-4d28-64a1-567a-f691c615870f | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 018E325B7D1CFC3B | xpl950_beachmaze.wad | ede160a5-4530-f55a-7667-f5a39257843c | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 0B6DF6C03C11EAB1 | xpl900_islandarch.wad | 23d3213f-45e3-8b63-2ed8-048e876e472d | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 0B6DF6C03C11EAB1 | xpl900_islandarch.wad | 9226bd44-4f0f-0b95-dbeb-7c927c6b317b | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 2FDD4E80C774CB0E | xpl910_islandshipwreck.wad | 9c0dc602-456a-00fa-44bc-a1a3b599cf67 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 2FDD4E80C774CB0E | xpl910_islandshipwreck.wad | d6fb0fd6-4364-453c-c3e3-34a2454e0b75 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 329C09A6AB45B3C4 | cal740_leftwing.wad | f714d2d8-45a3-dd9e-2880-8db4655e757f | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 3E2B34150449C3E7 | xpl400_huldramines.wad | 9d7648ab-43bf-99f9-0b0c-bd86b0a998f1 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv475_freyahouseext.wad | 11e085df-4bd4-7dee-e3a3-448bff9efc62 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv925_freyacave.wad | 36cb588e-41cb-27a4-6680-52b4529b98a6 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv925_freyacave.wad | 3c05899e-46a6-1901-5d4c-fb995fb61be0 | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv100_dangersentrance.wad | 8aabd22a-44df-8f25-a955-fe8e04fc0d95 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv925_freyacave.wad | ae9454d5-4e9c-9a23-f219-41b41a4038d3 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 62F2A92841484ABF | foot400_arena.wad | 0a04b4de-469f-3b03-0064-d6827966b213 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 62F2A92841484ABF | foot200_mid.wad | 510bd864-41ac-6a7b-71d4-f59321c2a08f | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 6732D984CAA9285A | xpl980_beachwaterfall.wad | 50480b3a-40fe-25c4-770f-81a7261cbcb8 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 6732D984CAA9285A | xpl980_beachwaterfall.wad | ace99ef5-472a-bcba-c29b-d2b396a3fdf3 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 6CB9C4F417D29A91 | xpl920_islandclimb.wad | 52934398-4fc3-1350-4ac2-0da874d05c01 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 7071EB6E695042F0 | xpl300_stronghold.wad | a24ac28d-4ea8-598d-880d-7bb099b8b8be | unresolved | blocked_unresolved_classification |
| legendary_chest | Legendary | 7CE593BC21393690 | 7880D593C85F2451 | xpl850_dungeonforest.wad | 7a71d104-452e-16e3-9a25-bb8a14e47343 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 7B7F0B522FFA9124 | cal100_hub.wad | 5b424870-484e-691c-e32d-19be71a03059 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | 848BB2D584D32E1B | stn200_lakeext.wad | 0e27df5f-4bc5-f254-5a43-178d0115312b | unresolved | blocked_unresolved_classification |
| legendary_chest | Legendary | 7CE593BC21393690 | 9391E1AF5C0C0C70 | xpl960_beachship.wad | b9e3be9a-46c2-48cc-0ddc-159643259c52 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl250_funeralinterior.wad | d6d6acfe-444f-2ad1-0b49-cea2ba85a1eb | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | A5D1DD6B44950CA7 | cal500_runevault.wad | d0b93e27-4754-785e-0823-5285bd6b78f2 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | ED623FA0A76B2934 | peak200_chimneylow.wad | 9f29650a-4a8a-5d0e-b8bc-43af1dbd3d68 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | ED623FA0A76B2934 | peak720_summitascenthub.wad | d63295f2-44f3-3021-9b00-3c913c0dab69 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | 7CE593BC21393690 | ED623FA0A76B2934 | peak500_chimneytop.wad | ff46dfab-43ef-cfc6-f0f3-82a33e2b571d | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel100_calderaheldressing.wad | 5618d560-4269-40a0-2e5b-39a340c0c209 | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel100_calderaheldressing.wad | 8002f429-4486-1752-3d18-9cbd93b23d4b | tracked_candidate | blocked_direct_binding_and_marker_path |
| legendary_chest | Legendary | FE4E39694E7F6B29 | FE4E39694E7F6B29 | helr100_docks.wad | 8266c175-474b-43a4-d449-38a75e21329d | explained_untracked | excluded_from_map_accounting |
| legendary_chest | Legendary | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel300_mainbridge.wad | 957a57b3-456b-d17f-d247-51a66dbcf01c | tracked_candidate | blocked_direct_binding_and_marker_path |
| lore_marker | native_lore_marker | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf150_bridgedark.wad | cb0f2576-4965-0034-5bb7-f18fcf0fd1dc.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf150_bridgedark.wad | f0459e96-4184-762f-6655-ec92d4bf6e04.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf440_hiveextlh.wad | 9e53750f-4709-bc19-466f-4dbad29509e9.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf690_lakelightlh.wad | 1ffb23e7-4aef-e162-5e9a-d1947306eeed.1c974485-4291-ea5a-a422-df90ac25672c.65a52500-4e93-fd6a-88e1-ad99f81b98f1 | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 46D26BEB5395C163 | 46D26BEB5395C163 | nid150_calderabridge.wad | ebc6ab2e-40fd-dac9-1ab4-4cb3d4d2fb6e.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 0000489975E7755D | xpl125_httklh.wad | 6c9af936-4b17-3785-fb95-abba5564949c.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 0000489975E7755D | xpl170_httkcaver.wad | e1516677-49cd-0b6e-ada2-ea956af5723d.af70ec7c-4fdb-e454-f0e1-968ff2e049d5 | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 254A1280A3285151 | xpl650_masontrailcave.wad | 07bff0b2-4a3e-3105-fd33-7ba2650639dc.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 3E2B34150449C3E7 | xpl400_huldramines.wad | 5d1a70e1-4596-52df-1f37-42b420521381.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 3E2B34150449C3E7 | xpl400_huldramines.wad | 94bd14f0-497b-6e36-af08-e0ad969375f0.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 3E2B34150449C3E7 | xpl425_huldramineslh.wad | 966d237f-4dc1-e38b-87de-ecb2a068a87f.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | level_script_lore_marker | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv925_freyacave.wad | ab859d0b83766845bb0b0e69023e1c31 | accounting_object_link_unresolved | blocked_exact_object_link_and_state |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv085_dangersentrancelh.wad | 56c55903-485b-ca88-4acf-66bdd3be6ee5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv200_dangersmain.wad | 62c42d45-4081-b2aa-a7c9-a89758c516d2.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv420_forestboarstart.wad | 2911670c-4c14-b3ec-41a6-f4bc660b15a3.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv475_freyahouseext.wad | 30f32451-428e-1a46-459c-65b1298ce016.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv475_freyahouseext.wad | 3a24509a-4492-7a69-5c9d-d481ac80c843.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv475_freyahouseext.wad | ca48c3db-4cba-d731-9c81-e995de95300e.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 7071EB6E695042F0 | xpl300_stronghold.wad | 0b70d779-47cf-e8c6-0354-7ba797526a41.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 7071EB6E695042F0 | xpl300_stronghold.wad | b4f161e3-4b07-4ca0-6362-8984ab395046.af70ec7c-4fdb-e454-f0e1-968ff2e049d5 | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 7B7F0B522FFA9124 | cal250_foothillslh.wad | 77b8b68a-4b2c-06e9-370f-0d9fc126825e.ca48c3db-4cba-d731-9c81-e995de95300e.af70ec7c-4fdb-e454-f0e1-968ff2e049d5 | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 7B7F0B522FFA9124 | cal250_foothillslh.wad | b2e61496-4b4f-d3df-b532-e98621a6299e.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 7B7F0B522FFA9124 | cal250_foothillslh.wad | 1f3856b4-49b4-8ff9-65cb-6a89fa24a49c.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 7B7F0B522FFA9124 | xpl910_islandshipwreck.wad | 5a999360-4bad-f7aa-bed1-309884067d0d.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 7B7F0B522FFA9124 | xpl940_beachcave.wad | 5a999360-4bad-f7aa-bed1-309884067d0d.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 7B7F0B522FFA9124 | xpl950_beachmaze.wad | 5a999360-4bad-f7aa-bed1-309884067d0d.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 7B7F0B522FFA9124 | xpl960_beachship.wad | 5a999360-4bad-f7aa-bed1-309884067d0d.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | 848BB2D584D32E1B | stn200_lakeext.wad | c39d3064-438d-e46d-abf5-098492fc5bb7.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | b193b90a-412f-a407-9c74-27af8d724866.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | 9fafcef8-4cef-59df-39d4-b6979dbb228b.af70ec7c-4fdb-e454-f0e1-968ff2e049d5 | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl220_funerallh.wad | 73c5a6ee-4992-5321-a88c-d5a4cb27a4b9.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl225_funerallh.wad | 3b198db1-4043-a37b-0e1d-83a84e1bfe10.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl225_funerallh.wad | 6c8f3cfb-4d46-6b09-2092-a8af548c2e01.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl250_funeralinterior.wad | daaeddd1-47ac-dbc0-8a71-44841192f0c1.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | level_script_lore_marker | 7CE593BC21393690 | AA75374C6FBBE8A6 | cal740_leftwing.wad | 3d2e2f04d7df6a4b9a4e30601432871f | accounting_object_link_unresolved | blocked_exact_object_link_and_state |
| lore_marker | native_lore_marker | 7CE593BC21393690 | AA75374C6FBBE8A6 | cal500_runevault.wad | bb72f414-492e-9d0d-4c77-d093025e74bb.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | level_script_lore_marker | 7CE593BC21393690 | AA75374C6FBBE8A6 | cal750_rightwing.wad | d988f2795775914592a04b62df2726d9 | accounting_object_link_unresolved | blocked_exact_object_link_and_state |
| lore_marker | native_lore_marker | 7CE593BC21393690 | ED623FA0A76B2934 | peak100_entrance.wad | 74d8a4ed-4be6-ea59-56c5-a1a00958c9ec.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | ED623FA0A76B2934 | peak140_caverndark.wad | a661ae3a-40c3-8169-dce3-d982399a4bb0.ca48c3db-4cba-d731-9c81-e995de95300e.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | ED623FA0A76B2934 | peak180_enttochimneylh.wad | d5f854cc-4509-9be6-dc4d-67a312642664.ca48c3db-4cba-d731-9c81-e995de95300e.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | ED623FA0A76B2934 | peak200_chimneylow.wad | c3fea329-4513-8231-bb8a-458aa239b40d.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | ED623FA0A76B2934 | peak500_chimneytop.wad | 8f929b1d-40ab-7e5f-2ec5-f9828067052e.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| lore_marker | native_lore_marker | 7CE593BC21393690 | ED623FA0A76B2934 | peak720_summitascenthub.wad | f17881da-458d-7e35-7e65-2a92d80d756e.af70ec7c-4fdb-e454-f0e1-968ff2e049d5.d42afb7d-46cb-abc8-4ed1-378ae492032f | direct_parent_state_blocked | blocked_persistent_state_and_marker_path |
| nornir_bell | bell | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf320_trenchadark.wad | aacfd881b995cd478f374320d33f7386 | unclassified | blocked_unclassified |
| nornir_bell | bell | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf690_lakelightlh.wad | 3da5ded1910991449f7166a3e62a76f0 | unclassified | blocked_unclassified |
| nornir_bell | bell | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf320_trenchadark.wad | 280ca156f81a864a9fb4c35e50c96774 | unclassified | blocked_unclassified |
| nornir_bell | bell | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf320_trenchadark.wad | 38f47b548fc94848a4e900996030eee5 | unclassified | blocked_unclassified |
| nornir_bell | bell | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf210_lakedarklh.wad | 87e830727d7a9c45a0ae5cc9d442bac9 | unclassified | blocked_unclassified |
| nornir_bell | bell | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf690_lakelightlh.wad | 5fb1391d16c8e3479aa1b246b7fad0f4 | unclassified | blocked_unclassified |
| nornir_bell | bell | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf210_lakedarklh.wad | 8b87e05c943d334298501ed5ae19bf62 | unclassified | blocked_unclassified |
| nornir_bell | bell | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf690_lakelightlh.wad | bfb6bd7642a3644c9e63ed58fbf2b797 | unclassified | blocked_unclassified |
| nornir_bell | bell | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf210_lakedarklh.wad | 0429e2da53b6884c9b97d0274ca8ed4d | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 0000489975E7755D | xpl100_httk.wad | bd61ac4bacd69a4188d927cb08049b7d | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 0000489975E7755D | xpl100_httk.wad | f874a07e12862145bf3b9be2be89d4a4 | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 0000489975E7755D | xpl100_httk.wad | 320f947c01717f4b9414c700dec214c8 | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 018E0CE2EAEAA53D | xpl940_beachcave.wad | 43bb2f4a93c84b48a973ce319ff73ce3 | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 018E0CE2EAEAA53D | xpl940_beachcave.wad | 7858594431946a43a274849bbab277e7 | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 018E0CE2EAEAA53D | xpl940_beachcave.wad | fb36be908dcbc94db9561a7c00c02690 | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 3A9BFC89F5AB6FE3 | xpl970_beachtower.wad | da3513f534e0954db68c1783b5a0003d | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 3A9BFC89F5AB6FE3 | xpl970_beachtower.wad | 693c72fcf5ef194c86d0eb46025f3e2f | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 3A9BFC89F5AB6FE3 | xpl970_beachtower.wad | 94e138354035204892d2837b56417df5 | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv420_forestboarstart.wad | 698aa710f2bd15479af3d51bc8644a4a | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv420_forestboarstart.wad | 6fb44a068e128449b4c3805538854813 | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv420_forestboarstart.wad | 251e823309507149bf02f80430fada9a | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 7880D593C85F2451 | xpl850_dungeonforest.wad | b7a497fd71c9c34ba8526acb0ee5f9e7 | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 7880D593C85F2451 | xpl850_dungeonforest.wad | c3772fe3ca1b8c48ae2c347090ae12e6 | unclassified | blocked_unclassified |
| nornir_bell | bell | 7CE593BC21393690 | 7880D593C85F2451 | xpl850_dungeonforest.wad | d59a44acb701e242960b5dad5cd3e988 | unclassified | blocked_unclassified |
| nornir_chest | Runic_Axe | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf320_trenchadark.wad | 3ec0daa8-4892-2cad-4fb3-0c8bb93c171f | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf690_lakelightlh.wad | 522448bf-4d91-b0f1-9de6-adbd1c77d709 | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf340_trenchbdark.wad | 9a92c243-4083-2c21-07ff-7d997c9fcbda | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf210_lakedarklh.wad | e00c75d2-4c76-b498-de4c-1f85c997c65e | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 0000489975E7755D | xpl100_httk.wad | d8e4c774-44fe-09d0-a960-198ab802058e | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 018E0CE2EAEAA53D | xpl940_beachcave.wad | a2cdfc7a-4f0a-b68e-ac21-2bb108cd35b7 | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 018E325B7D1CFC3B | xpl950_beachmaze.wad | c02f0190-49d5-0ea0-146c-478fd46f4a49 | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 3A9BFC89F5AB6FE3 | xpl970_beachtower.wad | 6b701107-4e78-df82-ecd5-08b6b1a8444f | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv925_freyacave.wad | 0f0cc7ca-4842-3bb2-96f6-ddbed87a8f3b | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv225_dangerscave.wad | 45bbcd15-458c-d30c-3338-a7b3dab9b3d9 | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv475_freyahouseext.wad | 69780ade-492b-0891-1948-4199e5423527 | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv325_dangersexit.wad | 7d8b4043-40e8-ef8e-db40-96b3a1a1e3fc | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv420_forestboarstart.wad | d2cacb84-426f-d68d-504a-11ae125c2b62 | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 62F2A92841484ABF | foot100_base.wad | a6ac8eeb-4ea2-545a-b05d-f19e8ea6ee8f | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 6CB9C4F417D29A91 | xpl920_islandclimb.wad | a336e184-4ac7-c90b-6cd6-288e2cdab274 | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 7880D593C85F2451 | xpl850_dungeonforest.wad | 3f3a8e78-44ff-44f5-7da0-24b2efce93dc | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | 7AF9D3D169EFE9B7 | for600_spire.wad | 6d18634c-4e86-282d-1cfa-0e84f6d5654f | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | c190d593-4070-6bb7-9925-cb9f2d5867cf | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | AA75374C6FBBE8A6 | cal500_runevault.wad | f8548c57-4dc6-7cba-277c-5cb31099648b | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | ED623FA0A76B2934 | peak720_summitascenthub.wad | c0cf4119-40ba-d7d0-0042-afa7a46f5514 | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | 7CE593BC21393690 | ED623FA0A76B2934 | peak140_caverndark.wad | f8ac74b9-414e-59e7-64d8-738182c00663 | tracked_candidate | blocked_direct_binding_and_state |
| nornir_chest | Runic_Axe | FE4E39694E7F6B29 | FE4E39694E7F6B29 | helr100_docks.wad | 6fc8ac79-4c63-bf63-a137-36b7cd3c7f25 | explained_untracked | excluded_from_map_accounting |
| nornir_mechanism | mechanism | 7CE593BC21393690 | 018E325B7D1CFC3B | xpl950_beachmaze.wad | 69287e03e0e3654885f077dd561289b4 | unclassified | blocked_unclassified |
| nornir_mechanism | mechanism | 7CE593BC21393690 | 018E325B7D1CFC3B | xpl950_beachmaze.wad | c6554c82a79e1d4e982b1e05f04bbdd6 | unclassified | blocked_unclassified |
| nornir_mechanism | mechanism | 7CE593BC21393690 | 018E325B7D1CFC3B | xpl950_beachmaze.wad | 45936e57e6647b478221f95758245876 | unclassified | blocked_unclassified |
| nornir_mechanism | mechanism | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv475_freyahouseext.wad | cc03f4374032004bb098393077592236 | unclassified | blocked_unclassified |
| nornir_mechanism | mechanism | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv475_freyahouseext.wad | 17267bc3a926f341b7edaf470cacff5a | unclassified | blocked_unclassified |
| nornir_mechanism | mechanism | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv475_freyahouseext.wad | 89539cb3c89ad642ace67a5c6e61e437 | unclassified | blocked_unclassified |
| nornir_mechanism | mechanism | 7CE593BC21393690 | 62F2A92841484ABF | foot100_base.wad | 0c82ef8386951f41a3c9aec3b0e7843a | unclassified | blocked_unclassified |
| nornir_mechanism | mechanism | 7CE593BC21393690 | 62F2A92841484ABF | foot100_base.wad | 91ff9d1d04d262409455906b045bbb36 | unclassified | blocked_unclassified |
| nornir_mechanism | mechanism | 7CE593BC21393690 | 62F2A92841484ABF | foot100_base.wad | 9f8795ae52c32d4daf909e8e44657e23 | unclassified | blocked_unclassified |
| nornir_mechanism | mechanism | 7CE593BC21393690 | ED623FA0A76B2934 | peak140_caverndark.wad | bb6cdebdd1907a4893077d8a1edfea19 | unclassified | blocked_unclassified |
| nornir_mechanism | mechanism | 7CE593BC21393690 | ED623FA0A76B2934 | peak140_caverndark.wad | 2fe3962e3a0b03439c91b360501b0c0a | unclassified | blocked_unclassified |
| nornir_mechanism | mechanism | 7CE593BC21393690 | ED623FA0A76B2934 | peak140_caverndark.wad | 324b4e851b20554e8d4a279a46809fbd | unclassified | blocked_unclassified |
| nornir_seal | seal | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf340_trenchbdark.wad | 2f417c41ecc82d40baec74e26d216c8d | unclassified | blocked_unclassified |
| nornir_seal | seal | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf340_trenchbdark.wad | ebd6aabf57d4a24b9ed41dde97c63d8d | unclassified | blocked_unclassified |
| nornir_seal | seal | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf340_trenchbdark.wad | ca03239e9d2540418fdcb66eeb56016f | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv925_freyacave.wad | 7ed429776db50d48a6a9118715036711 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv225_dangerscave.wad | 82f30792afff9e46b5e3b9a7c46bf7d7 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv325_dangersexit.wad | 641e06a42792a3498481a1c78991ea91 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv225_dangerscave.wad | 4c7d45e3d405224dadff0e049d8ced92 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv325_dangersexit.wad | c6fcb096df94b14c9a8f307a48dfbaed | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv325_dangersexit.wad | 43f15c9869a832449264946114a9ff5a | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv925_freyacave.wad | 34a3f409bd41734c8bf5290358efded7 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv925_freyacave.wad | 41ecf2d0fd74fe49b3c8a85d1febc914 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv225_dangerscave.wad | a36ee69bbc6ec248b7da8667b78afa74 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 6CB9C4F417D29A91 | xpl920_islandclimb.wad | aad078d8b6d53b40941f335e16dcb700 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 6CB9C4F417D29A91 | xpl920_islandclimb.wad | a233809feb563545b4685cad8dbd4f0b | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 6CB9C4F417D29A91 | xpl920_islandclimb.wad | 7b2c6fc8325e99439cfb3ca61a177d24 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 7AF9D3D169EFE9B7 | for600_spire.wad | fb57ea38de6b3a4a9d9dfe9ae0f3f12a | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 7AF9D3D169EFE9B7 | for600_spire.wad | 32527c108359f745bf98cfa8e553c776 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | 7AF9D3D169EFE9B7 | for600_spire.wad | 1459c53d0848224a9171ddf1c35699ff | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | cbcfec14c375e64d8e14a5f1004bb5fc | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | 49dcd39ea3bf604fab4fcbd1ed6628b0 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | d04d1d8a539e5b449369a4f562c2b756 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | AA75374C6FBBE8A6 | cal500_runevault.wad | 1d75521448e55d48b0c15253e0739ea5 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | AA75374C6FBBE8A6 | cal500_runevault.wad | 124f7e4eb805de44bc41fd584b695048 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | AA75374C6FBBE8A6 | cal500_runevault.wad | f72cd2d2d15d8944bc2e7b5340048a70 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | ED623FA0A76B2934 | peak720_summitascenthub.wad | 89f9d966b8be2846824db0d94d26ffb0 | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | ED623FA0A76B2934 | peak720_summitascenthub.wad | 61e82e15d6fdfe4ebbb2e917390f5dde | unclassified | blocked_unclassified |
| nornir_seal | seal | 7CE593BC21393690 | ED623FA0A76B2934 | peak720_summitascenthub.wad | 79accdd056c94145a958d65a691f4668 | unclassified | blocked_unclassified |
| nornir_seal | seal | FE4E39694E7F6B29 | FE4E39694E7F6B29 | helr100_docks.wad | 8f55098604a60b47b1446db74fd7b392 | unclassified | blocked_unclassified |
| nornir_seal | seal | FE4E39694E7F6B29 | FE4E39694E7F6B29 | helr100_docks.wad | 4a182b21cbc6bd40b0d7522308f77294 | unclassified | blocked_unclassified |
| nornir_seal | seal | FE4E39694E7F6B29 | FE4E39694E7F6B29 | helr100_docks.wad | 7951e02fb586454f981ede9bae912961 | unclassified | blocked_unclassified |
| odin_raven |  | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alfdgn210_main.wad | 63f2a1a7-4274-de6d-f396-2490fb6552e9 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 25B5C98A27101CB7 | 25B5C98A27101CB7 | alf355_chiseldungeon.wad | 95b9c644-4d47-9ac6-8207-b1829d02909b | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 0000489975E7755D | xpl100_httk.wad | 09c20f1b-4447-6543-307d-8d8a444401f7 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 0000489975E7755D | xpl150_httktemple.wad | 4f3ed860-4f52-3296-54cb-89a77cb7b227 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 0000489975E7755D | xpl100_httk.wad | 93bb4162-43c6-d7af-d0da-df824507fcb6 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 0000489975E7755D | xpl100_httk.wad | b65148ce-4018-9997-a7ee-6abb05551d95 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 0000489975E7755D | xpl170_httkcaver.wad | ce4340a8-4992-a449-844e-0394671c59eb | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 018E0CE2EAEAA53D | xpl940_beachcave.wad | 7ffe9f6e-4e18-734c-ebad-c892d24801e4 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 018E0CE2EAEAA53D | xpl940_beachcave.wad | bc9c2cea-4b7e-1fea-f09b-b58f1b691035 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 018E325B7D1CFC3B | xpl950_beachmaze.wad | 2b86b2ad-4f6c-006d-5f6d-b0af57a190a4 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 0B6DF6C03C11EAB1 | xpl900_islandarch.wad | 9deba511-4d80-4589-8daf-c5be9add793b | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 254A1280A3285151 | cal270_stonemasonlh.wad | fa8d596f-445b-a456-bc5b-11905aa4af07 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 2FDD4E80C774CB0E | xpl910_islandshipwreck.wad | 62fbf37c-443c-70ae-ca40-ac840f6084b1 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 3A9BFC89F5AB6FE3 | xpl970_beachtower.wad | 11d08355-4dd3-20d5-e23c-cca24f339acd | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 3E2B34150449C3E7 | xpl425_huldramineslh.wad | 0b07c75f-438c-e0cf-e8b6-feb7731ffc9c | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 3E2B34150449C7F6 | xpl475_huldramineslh.wad | 349cc1eb-4752-a614-9cf8-9f9f94644092 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 3E2B34150449C7F6 | xpl450_huldramines.wad | d869e607-4410-4a9e-8865-428d5fc2f63a | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv200_dangersmain.wad | 100bb5c4-4d6b-69eb-a68e-b895d005f956 | accounting_membership_unresolved_surplus_group | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv975_chiselarena.wad | 5a652cfb-4af8-6af5-17b3-3c8676dbbfc5 | accounting_membership_unresolved_surplus_group | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv400_forestintro.wad | 97e41c48-491b-177e-8040-19a649735e58 | accounting_membership_unresolved_surplus_group | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv475_freyahouseext.wad | ac45261c-43ee-745c-d2e2-0a9cf61a817d | accounting_membership_unresolved_surplus_group | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv420_forestboarstart.wad | ccbc62d6-4eb0-f79b-bf76-e9a08401a137 | accounting_membership_unresolved_surplus_group | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv200_dangersmain.wad | d9db9191-4694-cfe7-3fa5-b9abb208d25d | accounting_membership_unresolved_surplus_group | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 4EFD98E8E80E1239 | riv430_forestboartrack.wad | f8fdd3a4-438c-9697-f8aa-308323b2465e | accounting_membership_unresolved_surplus_group | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 62F2A92841484ABF | foot500_top.wad | 2862a927-444b-f9df-95a6-05b6a1cfec2b | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 62F2A92841484ABF | foot250_chiselarena.wad | e4d9b53e-4e03-30fc-0742-1d8fea348f1d | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 6732D984CAA9285A | xpl980_beachwaterfall.wad | ef856800-4bd6-283b-79b4-819bb3e5cb0f | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 7071EB6E695042F0 | xpl300_stronghold.wad | 7ea7fe24-483d-f9d8-84fd-4790840bf692 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 7071EB6E695042F0 | xpl300_stronghold.wad | e01f95a8-4dd1-e99d-de09-52856855399d | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 7880D593C85F2451 | xpl875_dungeonforestlh.wad | 14a87a63-4013-9081-5b4e-4ab2b4e619d0 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 7880D593C85F2451 | xpl850_dungeonforest.wad | 3f0baac6-4058-89c7-4788-96801b6a637c | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 7880D593C85F2451 | xpl875_dungeonforestlh.wad | 97b753a9-4e06-9b45-a5e0-31b81a5b9f91 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 7880D593C85F2451 | xpl850_dungeonforest.wad | ad565217-40c7-4507-6417-e99ddf1dd7a4 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 7880D593C85F2451 | xpl850_dungeonforest.wad | b5ec8398-449f-573b-8a70-b7a4fb1154af | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 7AF9D3D169EFE9B7 | for260_chiseldungeon.wad | 528d3320-48f7-34d8-4b2f-8ca26b3abafc | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 7B7F0B522FFA9124 | xpl910_islandshipwreck.wad | 4b8990ee-4053-cd00-d132-99928da1a9fc | accounting_membership_unresolved_surplus_group | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 7B7F0B522FFA9124 | xpl930_beachruins.wad | df5a6f75-43fa-157f-4cd6-30a19c038deb | accounting_membership_unresolved_surplus_group | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 848BB2D584D32E1B | stn090_lakevista.wad | 8ca357c4-45d3-2c01-5159-d6b93e173686 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 848BB2D584D32E1B | stn110_chiselarena.wad | a70cd386-4089-85c8-bedb-c98a7aaed456 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | 9391E1AF5C0C0C70 | xpl960_beachship.wad | 73ac8954-45d9-6775-6cbf-34ac591ac205 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | 642d0d16-4af0-a5d4-076e-77933c549a5d | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | c945cb53-465b-58de-cfcb-d4a221cb5326 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | A1845BEF17F0E7BB | xpl200_funeral.wad | e32f7bab-42fd-7298-890f-6aa56a734562 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | ED623FA0A76B2934 | peak140_caverndark.wad | 45321357-4047-8ac1-0837-7e8b1c51a501 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | ED623FA0A76B2934 | peak260_chimneylowhall.wad | 5a498384-495d-5891-6e94-4883eb2c90bb | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | ED623FA0A76B2934 | peak210_rollerroomlh.wad | b88e14b5-4130-82e9-8c4d-9cadcbf6ad10 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | 7CE593BC21393690 | ED623FA0A76B2934 | peak205_chiselarena.wad | fb1ebb00-4216-311e-237c-36b23a10707b | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel300_mainbridge.wad | 2811daa0-4ce3-0f07-9ff7-58b3bf04369d | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel300_mainbridge.wad | 595d8539-4887-53c5-4fa4-71a46631e8c7 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel300_mainbridge.wad | 69a8e9f3-434c-d84b-48c7-c688094ed2e4 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel300_mainbridge.wad | 7ffab2af-4d6e-2c7e-7a9d-42a58943bdf1 | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel100_calderaheldressing.wad | a824e129-46c8-03e8-511d-a79bc52a193f | accounting_group_matches_target | blocked_accounting_membership_and_state |
| odin_raven |  | FE4E39694E7F6B29 | FE4E39694E7F6B29 | hel350_chiselarena.wad | b13e5202-4ecc-5909-d1fe-478ee2c54e8c | accounting_group_matches_target | blocked_accounting_membership_and_state |
