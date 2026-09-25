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
`physical.carrier` keys are proposed. A later two-save field capture observed
the serialized chest object hash pairs for Veithurgard and the Mountain, with
the Mountain opened carrier copied exactly into a save slot; see
`docs/research/nornir-two-save-checkpoint-evidence.md`. A general unloaded
state query remains unproved. The same capture found a component byte that
tracks six loaded seals, but its native `IsDestroyed()` binding and unloaded
meaning are not yet proved. Nornir-specific map/world assets,
marker path, and suppression target also remain unproved. No runtime build is
enabled and no Raven production file changes on this branch.

## Separate marker identity

God of War uses native marker UIDs, resource names, and compass classes here;
there is no second game ID to assign while these collectibles still belong to
God of War. The offline Nornir family namespace is
`Completionist_V105_Nornir_Family` / `55DBA02CB6055D9F`. This is an ownership
key for the build tooling, not an installed engine marker or a save ID.

`config/collectibles/v0.10.5/nornir-marker-namespace.json` reserves 22 chest
marker UIDs and 66 separate child marker UIDs. It binds every set of three
children to its exact physical chest. The namespace builder recomputes names and
UIDs from physical identities and checks them against all 53 v0.10.5 Raven
markers, the frozen v0.10.4 Raven marker, and every other collectible in the
static catalogue. It also rejects a Nornir entry that points at another
family's map resource or compass class. A conflicting UID, name, or ownership
edge fails the static gate before any native builder can consume the data.

Generate the reservation with `python3 tools/v0.10.5/nornir_marker_namespace.py`.
With `--game-root`, the same tool also reads the installed `mapmaster.dcb`,
`mapcoords.dcb`, and `compassgraph.dcb` and rejects any collision with native
marker, coordinate, helper, or export UIDs. The read-only audit in
`docs/research/nornir-installed-marker-id-audit.json` found zero collisions for
the 89 reserved UIDs (family namespace plus 88 markers) against the current
installed game tables. Its source hashes pin which installed files were read,
and its manifest hash pins the exact proposed Nornir IDs.
The current status is `OFFLINE_IDENTITY_RESERVATION_ONLY`; no Nornir marker has
been registered in game by this step. Native class/resource construction and
the unloaded state gate are still required before a runtime build.

Run `python tools/v0.10.5/nornir_static_gate.py --output
docs/research/nornir-static-gate.json`. Current result:
`BLOCKED_FAIL_CLOSED`, 22 physical, 21 tracked candidates, 66 linked children,
0 direct native bindings, 0 proved unloaded state lookups. The gate checks
catalogue/audit digest, evidence coverage, child links, marker identity
reservation, and weak join rules.
It uses the earlier source audit; it does not reparse WADs on each run.
The JSON now records checkout-byte `source_sha256` and LF-normalized
`source_lf_sha256`. This lets a pinned Git blob match the same evidence on
Windows, where checked-out JSON has CRLF line endings. Gate status stays blocked.
