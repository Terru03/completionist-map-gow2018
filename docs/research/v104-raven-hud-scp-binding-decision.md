# Raven compass HUD SCP binding decision

Status: `LOCAL_SCP_REQUIRED`

This decision applies to the dedicated `goCompletionistRavenHUD` compass-HUD chain on the pinned v0.10.4 `r_ui.wad` baseline.

## Why the three-payload shortcut is rejected

The stock compass HUD peers are the authoritative grammar for this loader path. DockPoint, FastTravel, Valkyrie, MAIN, and SIDE all place a 96-byte `0x10005` `SCR_UI` SCP payload directly inside each `0x10001` prototype group. The five SCP bodies are byte-identical, yet the stock file still authors each one locally.

The SCP sentinel resource ID is not a unique binding key. The physical-grammar report found 2,057 payload definitions with that ID and 211 distinct payload bodies. A zero-data link using the same sentinel therefore cannot be treated as a globally unambiguous substitute for the locally authored HUD payload without stronger binding proof.

The only observed zero-data sentinel links relevant to the Raven work are from the inserted working map-icon chain. That is useful precedent for map resources, but it is not stock compass-HUD precedent. The map prototype also has different authored node/member topology from the two-node compass prototype. It therefore does not justify deleting the local SCP from the HUD clone.

No stock compass peer provides a zero-data SCP-sharing precedent. The smaller `+3 payload / +2 WAD_R_UI` design remains blocked.

## Selected topology

The dedicated Raven compass HUD clone follows the complete authored DockPoint grammar:

- model group: 5 physical records, 1 payload
- prototype group: 5 physical records, 2 payloads
  - cloned `goProtoCompletionistRavenHUD`
  - byte-identical local DockPoint SCP payload
- root group: 3 physical records, 1 payload

Total candidate growth:

- `+13` physical records
- `+4` payload records
- `+3` `WAD_R_UI` accounting
  - `0x10001`: `+1`
  - `0x10005`: `+1`
  - `0x20001`: `+1`

The model reuses the existing Raven material and stock Dock mesh. The root reuses `goProtocompassicons`. No new material, texture, GPU payload, or mesh is required.

## Runtime contract

`CompletionistRaven.IconName` will bind to:

- source string: `goCompletionistRavenHUD`
- hash: `45E5C7943749F81C`

`CompletionistRaven.InWorld_tMPIcon_Name` remains the stock Dock value `0E24C47DE2F769CA` during this isolation test.

The working map Raven chain remains independent and unchanged.

## Safety gate

The next candidate must be built and validated entirely outside the game tree. A runtime test is not authorized until:

1. the four-payload `r_ui.wad` candidate reparses and round-trips byte-exact;
2. the local SCP is preserved byte-for-byte inside the cloned prototype group;
3. all original WAD records remain byte-identical after removing the new groups and normalizing only proven accounting bytes;
4. the DCB candidate changes only `CompletionistRaven.IconName`;
5. the WAD and DCB candidates pass a combined cross-file contract verifier.

Only after that combined gate passes may a separate reversible two-file installer be used.
