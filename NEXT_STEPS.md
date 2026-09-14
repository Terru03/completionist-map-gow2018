# Next Steps

Current branch has a complete offline static research catalogue. Do not install
or generate runtime markers yet.

1. Prove one read-only, unloaded per-instance state lookup using the catalogue's
   exact native composite keys. Test it first on an already-completed save and a
   fresh save. Unknown, missing, or malformed responses must stay hidden.
2. Resolve the one Nornir tracked-target gap: native `quests.dcb` totals 21, while
   20 fixed parents join unambiguously to a RunicChest region target. Do not use a
   guide coordinate or nearest-object match.
3. Resolve the Ship Head gap: target total is 10, while 9 physical placements join
   unambiguously. Keep the 45 state carriers versus 43 placements distinction.
4. Prove how Niflheim procedural chest instances expose stable runtime identity
   and generated XYZ. Never emit the 56 Legendary or 7 Nornir template expansions
   as fixed markers.
5. For Breakable seals, prove exact unloaded individual state. Bells and
   MemoryChest mechanisms have no durable individual completion in current
   evidence; keep them visible only while their parent is exactly known unopened.
6. Only after steps 1-5 pass, generate a fully reversible offline Lua/native
   candidate. Reuse Raven ownership, UID normalization, filter, teardown, and
   transaction invariants. Keep families disabled by default.
7. Run runtime static checks, deterministic build twice, rollback proof, then set
   `ready_for_runtime_test` true. Only then ask for a manual gameplay test.
