# Ship Head production status, 2026-09-23

Branch `codex/collectible-ship-heads` starts at accepted Raven base
`f665f61`. Static gate: **BLOCKED_FAIL_CLOSED**. Runtime generation: **off**.

Nine physical Ship Heads have exact source placements, 13 transform paths,
script carrier GUIDs, and direct `RegionSummary_*_Shiphead_Parent` object
attributes. The native tracked total is 10, with no proved tenth object or
reason for the extra count.

Per-object serialized GameObject keys and unloaded `ACQUIRED` state lookup
remain unproved. The earlier frozen save scan at
`archive/field-logs/source-scans/collectible-save-oracle-20260914-095525`
found no identity hits in its older 238-row catalogue; its catalogue hash
differs from this branch's current catalogue, so it is negative background
evidence, not a current per-row state verdict. Native marker/suppression path
and Ship Head-specific resource IDs remain unproved. The generic Artefact
marker names in the catalogue are placeholders.

Next static work: prove serialized state identity and unloaded lookup for each
placed object; resolve native total 10; trace stock map/world presentation;
derive separate Ship Head artwork, material, texture, config and text IDs.
Only then can this branch prepare an offline delivery build.
