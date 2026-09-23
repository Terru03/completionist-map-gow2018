# Artefact static gate — 2026-09-23

Branch: `codex/collectible-artefacts`, based on Ship Head evidence at `36bf343`. This pass read shipped WAD/DCB files offline. God of War stayed closed; no game or save file changed.

The regenerated catalogue keeps **45 physical Artefacts**: 9 Ship Heads, 9 Masks, 6 Alfheim items, 6 Cups, 6 Horns, 5 Brooches, and 4 Toys. All 45 have exact source WAD hashes, physical placement IDs, world points, and the same authored `goartifactscript` script GUID. Their catalogue state field is `state == ACQUIRED`; the stock artefact script proves `ACQUIRED = 3`. Persistent unloaded state lookup is unproved for all 45.

The accepted Ship Head gate proves a direct native `RegionSummary_*_Shiphead_Parent` attribute on each of its nine objects. Its native quest target is ten, with no tenth physical carrier proved. Eight Ship Heads have exact frozen staged identity matches. These facts apply to Ship Heads only.

The broad generator had assigned `RegionSummary_CALS_Shiphead_Parent` to one Toy (`for200_house.wad`) and one Mask (`riv350_calderavista.wad`) through `unique_region_family_inference`. Neither exact script override contains that parent text. `artefact-cross-subtype-parent-audit.json` pins both WAD hashes, record IDs, and offsets. The generator now disables region-only quest inference for all Artefacts; exact native attributes still attach the nine Ship Head parents. Physical count stays 45; rows with a parent drop from 11 to 9. This fixes a false accounting join, not a collectible exclusion.

`artefact-static-gate.json` is `BLOCKED_FAIL_CLOSED`. It keeps 36 other Artefacts without a proved RegionSummary binding. Their absence of a RegionSummary parent does not prove they are untracked by all game systems. The generic `goMapIconCompletionistArtefact` and `CompletionistArtefact` names are catalogue placeholders; subtype artwork, native marker coverage, suppression, and unloaded state query remain open. No runtime marker output is allowed.

Rebuild and check:

```text
python tools/v0.10.5/collectible_catalogue.py --output config/collectibles/v0.10.5/all-collectibles.json --audit docs/research/all-collectibles-native-audit.json
python tools/v0.10.5/audit-artefact-parent-inference.py --output docs/research/artefact-cross-subtype-parent-audit.json
python tools/v0.10.5/ship_head_static_gate.py --output docs/research/ship-head-static-gate.json
python tools/v0.10.5/artefact_static_gate.py --output docs/research/artefact-static-gate.json
```

Next static step: trace subtype-specific quest/Labor accounting and serialized identity for the 36 non-Ship-Head rows. Keep Ship Head's 9/10 discrepancy separate.
