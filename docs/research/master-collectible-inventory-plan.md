# Master collectible inventory research gate

Branch: `codex/master-collectible-inventory`.

Purpose: build one canonical, inspectable inventory of every fixed completion-relevant object we may want to represent in Completionist Map, while preventing duplicate stock markers and preventing guide data from becoming runtime authority.

## Authority order

1. Shipped GoW native data and positive runtime state evidence.
2. Repository-derived static identity/ownership/state evidence.
3. External guides only as count/location audit or discrepancy detectors.

A guide can reveal that native research is incomplete. It can never create a physical row, persistent identity, completion state, or marker by itself.

## No duplicate-marker rule

Every inventory row carries a `mod_marker_policy`. The initial policy classes are:

- `CUSTOM_MARKER_CANDIDATE`: research may eventually authorize a custom marker.
- `NATIVE_MARKER_NO_DUPLICATE`: inventory/audit only; never add another marker while the stock marker is adequate.
- `RESEARCH_REQUIRED`: marker status is unknown; stay fail-closed.
- `EXCLUDE_PROCEDURAL_OR_REPEATABLE`: never turn templates/repeatable rewards into fixed pins.

Initial explicit no-duplicate families are Valkyries, Valkyrie Queen, Mystic Gateways, and Shops. Other families must be audited before being promoted or excluded.

## External baseline

PowerPyx's complete 2018 guide reports 332 guide locations and the following family totals used as audit expectations: 15 Favors, 45 Artefacts, 38 Mystic Gateways, 16 Shops, 39 Lore Markers, 51 Odin's Ravens, 8 Valkyries, 1 Valkyrie Queen, 3 Dragons, 21 Nornir Chests, 34 Legendary Chests, 18 Realm Tear Encounters, 7 Hidden Chambers, 11 Jotnar Shrines, 13 Purple Language Cipher Chests, and 12 Treasure Maps. Its treasure guide documents a corresponding dig site for each treasure map; this project audits treasure maps and dig sites as separate physical marker families.

These numbers are expectations, not native proof. Known examples of why this matters:

- Ship Heads have nine physical objects even though native quest accounting has a target of ten; do not invent a tenth marker.
- Legendary research currently distinguishes normal tracked chests from arena/Surtr reward chest placements; raw chest placement count is not the same thing as guide collectible count.
- Realm Tears include objects that do not all count toward the ordinary 100% region total; preserve the distinction rather than flattening them into one counter.

## Output

`build-master-collectible-inventory.py` emits:

- `master-collectible-inventory.json` — canonical machine-readable research table.
- `master-collectible-inventory.csv` — spreadsheet-friendly row inventory.
- `master-collectible-inventory.md` — human-readable family audit and physical-row table.

Each normalized row can carry family/subtype, realm/region, WAD, physical GUID, world XYZ, parent summary, serialized identity evidence, unloaded-query status, native-marker evidence, marker policy, and source digest.

The runner exports nine files by exact fetched commit SHA: the broad Ship Head seed, the Raven catalogue and native audit, and the Nornir, Legendary, and Artefact catalogues and static gates. It archives their bytes, relative-path manifest, branch heads, and SHA-256 hashes. The builder replaces seed rows for these four families with their authoritative family rows, then applies audit/gate classifications by catalogue identity. It does not switch branches or touch game files or the game process.

The audit keeps separate fields for physical rows, native accounting target, tracked candidates, explained untracked rows, unresolved classification, and production readiness. Raven has 53 physical objects and a Labor target of 51. Its native parent audit narrows two surplus objects to CalderaShores (2 physical / 1 target) and Riverpass (7 / 6). It does not identify the individual bonus object in either group. Nornir has 22 physical chests, 21 tracked candidates, one explained untracked Helheim reward, and 66 linked children. Legendary has 64 physical chests: 33 tracked candidates, 27 trial rewards, two non-map-counted physical chests, and two unresolved rows. Its external guide count of 34 remains a visible disagreement with the 33 native candidates.

Artefacts have 45 physical rows across seven subtypes. Nine Ship Heads have direct native parent attributes against a native target of ten. The other 36 lack proved RegionSummary membership; they remain physical and accounting-unresolved. The authoritative Artefact catalogue removes two region-only Shiphead parent inferences on a Toy and a Mask, with exact WAD override negatives archived on the Artefact branch. The external guide count of 45 cannot settle their accounting class.

Both current static gates hash their Windows CRLF checkout of `all-collectibles.json`; `git show` exports LF Git blobs. The builder checks both byte forms and rejects any content mismatch. It also validates gate row identities and classes against the pinned family catalogues. Neither gate grants production or marker permission.

## Gate

The master inventory is evidence-only. `runtime_generation_allowed` stays `false` even when a family count matches its external guide. A family can become marker-ready only through a separate positive native/runtime proof gate that establishes stable physical identity, world point, completion-state semantics, unloaded-state behavior where needed, and absence/inadequacy of a stock marker.
