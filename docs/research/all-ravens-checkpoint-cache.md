# All-Ravens per-save-point cache

## Goal

Completionist Map must remember Raven visibility across game restarts without
changing native Raven or quest progression.

Native `ravenKilled` remains the authority. The mod only caches what it has
observed so the map can be reconstructed before every Raven WAD is streamed.

## Field finding: core.save is WAD-scoped

Two in-save cache approaches were tested on 2026-09-18.

1. A cache updater exposed through a patched `core.save` module.
2. Direct calls from Raven scripts to
   `require("core.save").GetSaveState("__CompletionistMapV105Cache")`.

Both persisted data, but only for the resident Raven WAD.

The decisive diagnostic showed:

- `__CompletionistMapV105Cache` really existed inside `game.sav`;
- the compressed payload was mirrored in both save banks;
- restore replayed the cache successfully;
- MainHUD received the restored entries;
- only 3 Raven catalogue IDs were present.

Therefore the failure was not serialization or restore timing. The cache owner
itself was WAD-scoped, so travelling to another WAD did not build one global
53-Raven cache.

## Current design

GoW's save stores only an opaque mod-owned save-point ID:

```
__CompletionistMapV105SavePoint
```

The full Completionist snapshot lives outside the native save in:

```
mods/completionist-map-cache/<savePointId>.txt
```

The sidecar contains only observed catalogue state:

```
schema=1
savePointId=<id>
raven_<catalogue id>=0|1
```

MainHUD is the owner because its UI Lua state persists while travelling between
WADs and already receives every authoritative Raven state through the proven
`UI_CALL_EVENT` bridge.

## Save lifecycle

On a normal GoW save/checkpoint:

```
core.save.Save
  -> create opaque savePointId
  -> persist that ID in the WAD save state GoW was already going to serialize
  -> EVT_COMPLETIONIST_V105_SAVEPOINT_CAPTURE
  -> MainHUD writes its global observed Raven snapshot to the matching sidecar
```

On restore:

```
core.save.Restore
  -> read savePointId from the incoming checkpoint
  -> EVT_COMPLETIONIST_V105_SAVEPOINT_RESTORE
  -> MainHUD clears prior-session Raven cache
  -> load matching sidecar snapshot
  -> republish states into map runtime
```

If the save has no Completionist ID or the sidecar file is missing, the mod
fails open: no Raven is hidden from cache, and native WAD state repopulates the
cache as the player travels.

## Authority and safety

- A loaded Raven's native `ravenKilled` value always overwrites cached state.
- Killing a Raven still removes its map and compass marker immediately.
- The mod never sets `ravenKilled`.
- The mod never writes quest progress, labor counts, progression tokens, or
  native marker state.
- The only data added to GoW's Lua checkpoint state is the opaque save-point ID.
- Full Raven visibility state is stored in the mod sidecar directory.

## Fresh and old saves

- A fresh save with no sidecar starts with all 53 catalogue Ravens visible.
- An old pre-mod save seeds incrementally as Raven WADs are visited.
- Once that observed state is saved, future reloads of that exact save point can
  restore the global snapshot immediately.
- Loading an older save point uses its own embedded ID and therefore its own
  older snapshot instead of inheriting later Raven kills.

## Transaction scope

The controlled game-file candidate remains seven files, including:

```
mods/lua/gameart/scripts/libraries/core/save.lua
mods/lua/gameart/ui/scripts/hud/mainhud.lua
```

The installer additionally creates the user-data directory:

```
mods/completionist-map-cache
```

The directory is not a replacement game file and is not part of rollback
baseline hashing; it contains only Completionist Map cache data.
