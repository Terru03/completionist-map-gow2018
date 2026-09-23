# Realm Tear static gate — 2026-09-23

Branch: `codex/collectible-realm-tears`. This pass only read shipped `quests.dcb` and WAD files. God of War stayed closed. No game/save file changed.

Native quest data calls this family `PocketRift`. `quests.dcb` has ten `RegionSummary_*_PocketRift_Parent` targets totaling **19**. The user-supplied guide baseline is 18 Realm Tear Encounters, of which 11 are said to count toward normal completion. These are three different counts. No exact per-object reconciliation is proved yet.

`realm-tear-static-gate.json` pins the quest DCB SHA-256 and SHA-256 for each of 24 WADs containing `pocketrift` text. Fourteen placed override records contain an exact PocketRift Summary parent name. They include loot rift objects and Niflheim/HTTK reward chests. Each has a native override ID, offset, source WAD hash, world transform chain, and world point. These are **parent callback carriers**, not a proved census of physical Tear encounter entities. Their parent counts fill 14 of 19 native target slots. `RegionSummary_MUSP_PocketRift_Parent` has three target slots with no direct override carrier in this scan; `RegionSummary_RP_PocketRift_Parent` has two. The scan searched all shipped WADs for the PocketRift token and parsed matching WADs.

One Niflheim level script has `SetMarkerState` calls and `Nif_400_RealmTear01/02/03` names. This is positive native marker path evidence for those names only. Exact marker coverage and state behavior for every encounter stay open. A prefab `interact_loot_pocketrift` script exists, but persistent unloaded completion state and per-object encounter identity remain unproved.

Gate status is `BLOCKED_FAIL_CLOSED`: physical encounter census not yet proved, no physical rows generated, zero runtime permission. Do not import the 14 callback records as master Realm Tear rows or add custom markers from them.

Rebuild and test:

```text
python tools/v0.10.5/audit_realm_tear_native.py --output docs/research/realm-tear-static-gate.json
python -m unittest discover -s tools/v0.10.5 -p test_realm_tear_static_gate.py
```

Next proof: trace encounter prefab placements, scripted Muspelheim and Riverpass accounting, exact persistent completion states, and stock marker coverage. Keep procedural/repeatable cases distinct from fixed encounters.
