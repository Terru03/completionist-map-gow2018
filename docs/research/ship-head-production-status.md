# Ship Head production status, 2026-09-23

Branch `codex/collectible-ship-heads` starts at accepted Raven base
`f665f61`. Static gate: **BLOCKED_FAIL_CLOSED**. Runtime generation: **off**.

Nine physical Ship Heads have exact source placements, 13 transform paths,
script carrier GUIDs, and direct `RegionSummary_*_Shiphead_Parent` object
attributes. The native tracked total is 10. Shipped artifact script has a
conditional CALS summary increment after the Ship Head quest is complete.
This may explain CALS extra progress, but exact firing count and BW/BSW
regional target mismatch remain unproved. No tenth object is proved.

The shipped script defines `ACQUIRED = 3`, stores checkpoint state, and calls
`SoftSave()` after acquisition. Exact serialized GameObject keys match frozen
staged state for heads 01–07 and 09. Head 08 has no frozen match in either
path. Unloaded state lookup remains unproved for all nine. The earlier frozen save scan at
`archive/field-logs/source-scans/collectible-save-oracle-20260914-095525`
found no identity hits in its older 238-row catalogue; its catalogue hash
differs from this branch's current catalogue, so it is negative background
evidence, not a current per-row state verdict. Native marker/suppression path
and Ship Head-specific resource IDs remain unproved. The generic Artefact
marker names in the catalogue are placeholders.

Next static work: resolve head 08's serialized identity and prove unloaded
lookup for each placed object; resolve exact regional accounting; trace stock map/world presentation;
derive separate Ship Head artwork, material, texture, config and text IDs.
Only then can this branch prepare an offline delivery build.
