# Next Steps

## 2026-09-18 multi-family runtime implementation started

The static non-Raven catalogue is already complete enough to drive implementation:
240 rows total (45 Artefacts, 43 Lore, 64 raw Legendary Chests, 22 Nornir
Chests, 30 Seals, 24 Bells, 12 Mechanisms).

Runtime work now reuses `tools/v0.10.5/collectible_runtime_model.py` rather than
creating another visibility engine.

Completed in this pass:

- production eligibility gate: only `tracked_collectible` Legendary rows can
  render; 27 exact trial rewards and 4 unresolved rows fail closed;
- optional runtime family gate independent from the user's map filter;
- exact state bridge keyed by `source WAD + progression.instance_key`;
- 195 exact WAD/state identities are collision-free;
- raw `instance_key` alone is forbidden because four Lore placements share one
  key across different WADs;
- rollout contract lives in
  `config/collectibles/v0.10.5/family-rollout.json`;
- every non-Raven family remains runtime-disabled until its authoritative
  unloaded-state gate is satisfied.

Immediate implementation order:

1. Finish the read-only unloaded state oracle and return exact
   `WAD + instance_key + complete` replies.
2. Feed those replies through `CollectibleRuntimeModel.observe_instance()`.
3. Enable Artefacts first (45), then Lore (43), then the 33 tracked Legendary
   Chests. Unknown state stays hidden.
4. Keep Nornir runtime-disabled until the parent binding/state gates are
   resolved; then enable parent chests before child families.
5. Never emit fixed Niflheim procedural templates and never create the fake
   tenth Ship Head.


Static native catalogue now has all 9 proved Ship Heads. Do not build or install
runtime markers yet.

1. Prove read-only unloaded per-object state lookup with exact catalogue keys.
   Test known complete and fresh states. Unknown or bad reply must stay hidden.
2. Find exact reason `quests.dcb` says Ship Head 10 while native data proves 9
   carriers and 9 physical objects. Do not make fake tenth row.
3. Prove exact native binding edges for any of the 21 non-Helheim Nornir
   candidates. All old 20 joins are now downgraded because source WAD identity
   plus target existence does not prove object/level-to-target ownership. Also
   prove or reject exact link from cal500 placement
   `f8548c57-4dc6-7cba-277c-5cb31099648b` to
   `RegionSummary_RunicChest_Parent_TyrsVault`. Current callback/level labels do
   not prove RegionSummary update wire.
4. Resolve the remaining 4 nontracked Legendary-path chests only from positive
   native reward, quest, callback, or story wire. The other 27 nontracked rows
   are exact arena/Surtr trial rewards and stay production-excluded. Keep all 64
   raw rows.
5. Prove stable runtime ID and world point for Niflheim procedural chest spawn.
   Do not emit 56 Legendary or 7 Nornir templates as fixed markers.
6. Prove unloaded individual state for Breakable seals. Bell and MemoryChest
   children stay tied to exact known-unopened parent.
7. Only after state gate passes, make reversible offline runtime build. Families
   stay off by default. Run static checks, two deterministic builds, rollback
   proof, then ask for game test.

Current blockers:

- Ship target mismatch: `BLOCKED_EXACT_REASON_UNKNOWN`.
- All 21 tracked-candidate Nornir bindings: `BLOCKED_EXACT_REASON_UNKNOWN`.
- cal500 Tyr's Vault binding: `BLOCKED_EXACT_REASON_UNKNOWN`.
- Legendary production eligibility: 33 tracked, 27 exact trial exclusions,
  4 unresolved (`stn200`, `xpl300`, `cal500`, `cal740`).
- Exact unloaded per-instance state: `BLOCKED`.
- Runtime generation: `BLOCKED_FAIL_CLOSED`.

Helheim extra Nornir is explained: `PASS_EXPLAINED`,
`level_scripted_untracked_triple_chest_reward`.
