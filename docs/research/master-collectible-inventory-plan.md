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

The first runner uses the broad current all-collectibles catalogue from `codex/collectible-ship-heads` as a seed and pins the current Raven, Legendary, and Nornir branch heads for subsequent evidence imports. It does not switch branches and does not touch game files or the game process.

## Gate

The master inventory is evidence-only. `runtime_generation_allowed` stays `false` even when a family count matches its external guide. A family can become marker-ready only through a separate positive native/runtime proof gate that establishes stable physical identity, world point, completion-state semantics, unloaded-state behavior where needed, and absence/inadequacy of a stock marker.
