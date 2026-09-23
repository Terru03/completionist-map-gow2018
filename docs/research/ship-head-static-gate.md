# Ship Head static gate, 2026-09-23

Branch: `codex/collectible-ship-heads`. Base:
`origin/release/ravens-v0.10.5-proven` at `f665f61`. This branch is separate
from `codex/collectible-legendary-chests`.

This pass reads repository evidence from the shipped WAD/DCB census. It does
not launch God of War, read a live process, install a hook, or write a game or
save file.

## Physical and tracked identity

The base catalogue has 9 distinct Ship Head placements, 9 script state
carriers, and 13 exact transform paths. Numbered native object names cover
01–09. The `goartifactscript` source attribute names each row's
`RegionSummary_*_Shiphead_Parent` directly; the gate checks that this text is
in that object's exact script override bytes in the seven shipped source WADs,
pins each WAD digest and override record/offset, and checks that the named
target exists in the native summary audit. This is stronger than a WAD-name
or map-count join.

| No. | WAD | Physical GUID | Direct parent attribute | Paths |
| ---: | --- | --- | --- | ---: |
| 01 | `xpl910_islandshipwreck.wad` | `fda83783-4b36-1579-d4a2-9194810c3d09` | `RegionSummary_ISW_Shiphead_Parent` | 1 |
| 02 | `xpl970_beachtower.wad` | `01a8ba24-409b-5fb4-9a1c-18b43669fe44` | `RegionSummary_BT_Shiphead_Parent` | 1 |
| 03 | `xpl980_beachwaterfall.wad` | `379728fc-47e4-a966-be1f-c9926011184b` | `RegionSummary_BW_Shiphead_Parent` | 2 |
| 04 | `xpl950_beachmaze.wad` | `5bb11ed5-419b-42ca-ba81-3598d29ca473` | `RegionSummary_BM_Shiphead_Parent` | 1 |
| 05 | `cal100_hub.wad` | `4a3d3149-42f1-87f6-9ee5-b78302e118fe` | `RegionSummary_CALS_Shiphead_Parent` | 2 |
| 06 | `xpl940_beachcave.wad` | `7d8a35dc-4d6a-abf8-065e-1ead0c470fcc` | `RegionSummary_BC_Shiphead_Parent` | 1 |
| 07 | `xpl980_beachwaterfall.wad` | `6cffc988-4efa-77b4-24ba-f987adfdba6a` | `RegionSummary_BW_Shiphead_Parent` | 2 |
| 08 | `cal100_hub.wad` | `f7fbfc3f-4499-1b3d-a378-71879e6de737` | `RegionSummary_CALS_Shiphead_Parent` | 2 |
| 09 | `xpl960_beachship.wad` | `bd9a46a3-4b8f-d466-0be2-129e27fa4004` | `RegionSummary_CALS_Shiphead_Parent` | 1 |

The `quests.dcb` tracked total is 10. The shipped `interact_loot_artifact`
script has a `FixupShipHeadRegion()` path that increments
`RegionSummary_CALS_Shiphead_Parent` when `Quest_Artifacts_ShipHeads` is
complete. This gives a concrete scripted source for CALS progress, but its
exact firing count is unproved. Direct object counts versus regional targets
leave BSW +1, BW -1, and CALS +1. No tenth physical carrier is proved. The
gate keeps 9 physical hypotheses and does not invent a tenth row.

## State and delivery gaps

The stock `interact_loot_artifact` path defines `ACQUIRED = 3`, saves and
restores `state`, increments its `regionSummaryQuest`, and calls `SoftSave()`
after acquisition. The source Lua digest and matching compiled record in
`xpl940_beachcave.wad` are pinned by the gate. Each row has a physical GUID
and one or two script carrier GUIDs.
The 13 concatenated `physical.carrier` strings are old **proposed** keys.
An offline replay of the frozen staged WAD capture now matches exact serialized
GameObject/state keys for eight physical heads (01–07 and 09). Row 08 has no
match in either candidate path. The replay checks the Ship Head prototype root
in seven shipped WADs and tries all owner-chain subsets while holding each
script and physical placement. It found one match per resolved head, none on
alternate carrier paths. See `ship-head-staged-identity.json` and
`ship-head-staged-identity.md`. A frozen staged hit does not prove an unloaded
save query. Shared script carriers in rows 03/07 and 05/08 still make that
proof important. The gate requires
`unloaded_query=unresolved` for all 9 and will reject a catalogue-only claim
that it is proven.

An earlier frozen save scan found zero exact row identity hits across an older
238-row catalogue. Its catalogue digest differs from this base, so that scan
is negative background evidence only; it does not settle any current row.

The base catalogue's generic `goMapIconCompletionistArtefact` and
`CompletionistArtefact` names are placeholders, not proven Ship Head resource
IDs. A Ship Head-specific map icon, world marker, material/config IDs, stock
pin/marker suppression targets, and duplicate handling are not yet proved.
No Ship Head delivery code is enabled. Raven production files are unchanged.

The shipped `mapmaster.dcb` (SHA-256
`aec578e773898a1e60d5ccedd0df08e35b12ab54e4d26f4cd90740948430c2a0`)
contains six Shiphead summary-name strings and 382 `goMapIcon*` strings across
13 names, with no Artifact/Shiphead icon name. The shipped `r_ui.wad` (SHA-256
`92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04`)
has 53,777 parsed records and 119 distinct record names containing
`mapicon`; none names a Ship Head. It has no literal
`goMapIconArtifact` or `goMapIconShip`. These are narrow negative checks.
They do not rule out a dynamic marker path or prove that suppression is
unnecessary.

## Gate

Run `python tools/v0.10.5/ship_head_static_gate.py --output
docs/research/ship-head-static-gate.json`. Current result:
`BLOCKED_FAIL_CLOSED`, 9/9 physical rows, 13/13 paths, 0/9 proved unloaded
save lookups. Thirteen offline tests guard the row census, parent attribute,
identity paths, frozen staged keys, target gap, script semantics, state claim,
marker point, and shipped WAD check.
Source hashes in the JSON pin the catalogue and audit used by this check.
The gate reparses the seven known source WADs to verify each parent attribute
at its exact recorded script override.
