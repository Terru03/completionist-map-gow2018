# All-Ravens per-save-point checkpoint cache

## Purpose

Completionist Map keeps Raven visibility synchronized with native `ravenKilled` state while avoiding any writes to native Raven/quest progression.

The v0.10.5 checkpoint-cache design adds one mod-owned table to GoW's existing Lua checkpoint save state:

```
__CompletionistMapV105Cache
```

The cache stores only:

```
catalogue_id -> killed boolean
```

for catalogue Ravens whose native state has actually been observed.

## Authority

The cache is advisory. Native gameplay state is always authoritative.

- A loaded Raven's native `ravenKilled` value updates the cache.
- Native values overwrite older cache values.
- Killing a Raven still hides it immediately through the runtime-proven gameplay/UI bridge.
- No code sets `ravenKilled`, quest progress, tokens, labor counts, or native marker progression.

## Save-point behavior

Because the cache is serialized by `core.save`, it follows the exact checkpoint/save point:

- loading an older save restores that save point's older Completionist cache;
- reloading/restarting no longer requires revisiting already-observed zones;
- a fresh save has no cache and therefore defaults to all 53 catalogue Ravens visible;
- an old save created before this cache existed seeds incrementally as Raven WADs load, then future checkpoints retain those observations.

## Runtime path

```
native precisionchallenge ravenKilled
  -> CompletionistMapV105CacheRavenState
  -> __CompletionistMapV105Cache in core.save state
  -> normal GoW checkpoint serialization
  -> core.save Restore
  -> EVT_COMPLETIONIST_V105_RAVEN_CACHE_RESTORE
  -> MainHUD receiver
  -> map runtime state
```

The existing live path remains:

```
precisionchallenge
  -> UI_CALL_EVENT
  -> MainHUD
  -> map runtime
```

## Transaction scope

The controlled candidate now contains seven files, adding:

```
mods/lua/gameart/scripts/libraries/core/save.lua
```

to the prior six-file Raven candidate. It is backed up, SHA-checked, installed, and rolled back through the same transaction engine.
