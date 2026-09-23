# Nornir static gate, 2026-09-23

Branch `codex/collectible-nornir-chests` starts from accepted Raven base
`f665f61`, separate from Legendary and Ship Heads. This pass reads repository
WAD/DCB research only. God of War stays closed; no live process, hooks,
runtime capture, game writes, or save writes.

The base catalogue has **22 physical Nornir Chests** and **66 child objects**:
30 seals, 24 bells, and 12 mechanisms. Every parent has three children linked
by an exact Lua table attribute on the parent placement. The base audit lists
21 tracked candidates against a native target of 21, plus one Helheim
level-scripted triple-chest reward. This is the current repository census;
the older 34-row shorthand is not this catalogue's physical chest count.

The physical placements and source WAD identities are exact. For all 21
tracked candidates, the object/level-to-`RegionSummary_RunicChest` edge is
missing. Target existence, WAD name, region text, and total count do not form
that edge. The Helheim exception has a source callback and lacks a Helheim
RunicChest target, but it does not fix the other 21 joins.

`state == OPENED` is the loaded stock chest field. Current catalogue
`physical.carrier` keys are proposed; serialized per-object identity and
unloaded state query remain unproved. Nornir-specific map/world assets,
marker path, and suppression target also remain unproved. No runtime build is
enabled and no Raven production file changes on this branch.

Run `python tools/v0.10.5/nornir_static_gate.py --output
docs/research/nornir-static-gate.json`. Current result:
`BLOCKED_FAIL_CLOSED`, 22 physical, 21 tracked candidates, 66 linked children,
0 direct native bindings, 0 proved unloaded state lookups. The gate checks
catalogue/audit digest, evidence coverage, child links, and weak join rules.
It uses the earlier source audit; it does not reparse WADs on each run.
The JSON now records checkout-byte `source_sha256` and LF-normalized
`source_lf_sha256`. This lets a pinned Git blob match the same evidence on
Windows, where checked-out JSON has CRLF line endings. Gate status stays blocked.
