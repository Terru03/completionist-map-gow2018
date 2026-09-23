# Jotnar Shrine static gate — 2026-09-23

Branch: `codex/collectible-jotnar-shrines`. This pass read shipped `quests.dcb` and WAD files offline. God of War stayed closed. No game or save files changed.

Native quest data calls this family `Triptych`. `Quest_Triptychs_Objective` has target **11** in `quests.dcb`, with exact record offset and source SHA-256 pinned in `jotnar-shrine-static-gate.json`. The user guide baseline is also 11; equal totals do not prove each physical object's membership.

The WAD scan found 14 named Triptych override placements. `stn105_chiselsite.wad` and `stn905_chiselsite.wad` repeat the same Thamur override ID, name, and world point, so the report keeps both source records under one distinct placement. Result: **13 distinct named physical placements** with exact override IDs, WAD hashes, transform chains, and world points. The peak720 object is spelled `gotryptich_overrideInst` in shipped data; the scanner retains it. Separate `gotryptich_light_burst_overrideInst` records are effects and are excluded from the shrine placement census.

Eleven distinct placement WADs contain compiled `interact_triptych` Lua with `Quest_Triptychs_Objective`, `IncrementQuestProgress`, `OnSaveCheckpoint`, `OnRestoreCheckpoint`, and `triptychCompleted`. The two Tyr placement WADs (`cal170_library1.wad`, `cal590_runevaultelevator.wad`) lack that script. This is a strong candidate split, but it is still WAD context. Exact callback-to-object membership and a persistent unloaded completion query are unproved. The two Tyr placements stay physical and unclassified; neither is deleted to force 11.

Native marker coverage is not yet proved. Gate is `BLOCKED_FAIL_CLOSED`; all 13 named placements have `marker_generation_ready=false`. `exhaustive_physical_census_proven=false` until other object name paths are excluded or resolved.

Rebuild and test:

```text
python tools/v0.10.5/audit_jotnar_shrines_native.py --output docs/research/jotnar-shrine-static-gate.json
python -m unittest discover -s tools/v0.10.5 -p test_jotnar_shrine_static_gate.py
```

Next proof: inspect native Triptych prefab/script linkage for each placement, persistent checkpoint key/state, and map/compass marker coverage. Keep story Tyr placements separate from quest-linked candidates until object evidence settles them.
