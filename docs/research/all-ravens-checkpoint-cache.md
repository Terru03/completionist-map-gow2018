# Raven persistence experiments — disabled

## Current runtime contract

The active v0.10.5 Raven build does **not** persist Completionist state in GoW
save data and does **not** use a sidecar cache.

The field-proven behavior restored on 2026-09-18 is:

- all 53 catalogue Ravens are available to the map;
- native `ravenKilled` state is authoritative;
- a killed Raven disappears immediately from map/compass;
- when a Raven WAD loads, its already-killed Ravens are reconstructed and hidden;
- unloaded historical regions remain visible until their Raven WAD loads;
- no Completionist code writes Raven/quest/progression state.

The seventh transaction file, `core.save.lua`, is currently a pristine
pass-through copy only. It remains in the transaction temporarily so the
currently installed seven-file experimental build can be rolled back and
replaced safely.

## Failed experiment 1: WAD-local core.save cache

The first implementation stored Raven state under
`__CompletionistMapV105Cache` using GoW's `core.save` state.

Field diagnostics proved that serialization and restore worked:

- the cache existed inside `game.sav`;
- the payload appeared in both mirrored compressed save banks;
- `core.save.Restore` replayed the cache;
- MainHUD received the restored entries.

But only three Raven IDs were present. The save-state owner was WAD-scoped, so
travelling between regions did not aggregate one global 53-Raven snapshot.

## Failed experiment 2: save-point ID + MainHUD sidecar

The second implementation stored only an opaque save-point ID in GoW's save and
asked MainHUD to store the global Raven snapshot in
`mods/completionist-map-cache`.

Field testing failed persistence again and introduced a regression: some
previously-killed Ravens remained visible after a zone load.

The architectural cause was that WAD-local restore callbacks could invoke the
UI restore path multiple times. The sidecar restore path cleared the global UI
state, allowing a later WAD-local restore to erase authoritative Raven states
that another WAD had just published.

This experiment is removed from active tooling.

## Next persistence direction

Do not add another mod-owned cache until the authoritative global old-save
identity path is solved.

The remaining preferred route is read-only reconstruction from GoW's existing
save/checkpoint data, reusing the already-solved outer save carrier and
GameObject token codec plus the static 53-Raven catalogue identity work.

That preserves the intended contract:

- no save/progression writes;
- no external cache synchronization problem;
- exact state comes from the save being loaded;
- fresh saves naturally show all 53;
- old saves can eventually show only surviving Ravens immediately.
