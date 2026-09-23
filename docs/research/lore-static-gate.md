# Lore Marker static gate — 2026-09-23

Branch: `codex/collectible-lore-markers`. This pass read shipped WAD/DCB files offline. God of War stayed closed. No game or save files changed.

The catalogue keeps **43 physical Lore rows** in 34 WADs. Forty use native `langcheckruneread` objects. Three use level Lua script callbacks. All have pinned WAD SHA-256, exact override record IDs and offsets, physical IDs, and world points. The native quest Summary target total is 43. The user-supplied external guide count is 39. No object has been removed to fit that count; exact reasons for the difference remain open.

`lore-native-bindings-audit.json` reopens the shipped WAD for each row and checks its hash and exact object record. Forty object overrides directly contain their `RegionSummary_*_LoreMarker_Parent` name. Thirty-seven of those also hold a parsed journal ID; three have no journal ID in that override. The three level script WADs each contain `UpdateJournal`, the specific journal ID, `ActivateAndIncrementQuest`, and a Lore Summary name together in one compiled level Lua blob. Their chosen physical object's override contains neither ID nor Summary name. This proves a level script callback clue, but it does not prove the callback is bound to that exact physical object. The broad catalogue had mislabeled these three as `exact_native_object_attribute`; it now leaves their object parent null and keeps the script clue in this separate audit.

The 40 native rows use the `mapSummaryComplete == true` field in the catalogue. The three script rows use `bRuneReadStarted == true` (two) or `wellRead == true` (one). These are distinct state adapters. No persistent unloaded lookup has been proved for either. The catalogue's `goMapIconCompletionistLoreMarker` and `CompletionistLoreMarker` names are proposed IDs only. Native marker coverage, custom resource delivery, and suppression remain open.

`lore-static-gate.json` is `BLOCKED_FAIL_CLOSED`: 43 physical, 40 direct object parents, three level script clues, zero persistent unloaded states, zero production-ready rows. All marker generation remains off.

Rebuild and check:

```text
python tools/v0.10.5/collectible_catalogue.py --output config/collectibles/v0.10.5/all-collectibles.json --audit docs/research/all-collectibles-native-audit.json
python tools/v0.10.5/audit-lore-native-bindings.py --output docs/research/lore-native-bindings-audit.json
python tools/v0.10.5/lore_static_gate.py --output docs/research/lore-static-gate.json
python -m unittest discover -s tools/v0.10.5 -p test_lore_static_gate.py
```

Next proof: trace the three level Lua callbacks to exact rune objects, locate persistent unloaded fields for both state paths, and audit native marker coverage. Keep 43/39 separate until exact native evidence resolves it.
