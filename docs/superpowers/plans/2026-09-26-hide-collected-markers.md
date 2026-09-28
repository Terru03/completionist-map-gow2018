# Hide Collected Markers Implementation Plan

Updated 2026-09-27. Runtime and package are implemented and installed. Saved-state
coverage remains partial; missing bindings are listed explicitly below.

**Goal:** Hide a collectible marker when exact current-save state says `collected`.
Unknown state stays visible. Preserve working map, filters, marker identities,
compass behavior, Raven/Nornir ownership and the capacity fixes.

**Spec:** [Hide collected map markers](../specs/2026-09-26-hide-collected-markers.md).
**Build and rollback:** [Installed completion package](../../builds/v0.10.5-hide-collected.md).
**Coverage:** [Per-family evidence](../../research/collectible-state-coverage.md).

## Completed implementation

- [x] Freeze the working recovery package and pin its journal, executable,
  assets, script inputs and build sources. Keep independent completion backups.
- [x] Reconcile standard-chest/Nornir native bridge source and decoder fixtures.
- [x] Generate an ordered contract for all 410 IDs, excluding 27 repeatable rewards.
  Bind 33 Legendary identities using exact saved owners and archived decoding.
- [x] Compose one tri-state store before the location layer. Connect actual
  save boundaries, reset stale state and preserve terminal collection per epoch.
- [x] Add bounded native snapshot delivery with contract, nonce, generation,
  restore-epoch, code, size and cardinality checks. Normalize native chest enums.
- [x] Poll from the UI timer while the map is closed. Refresh save authority
  after load without requiring map open. Use elapsed UI time: absolute timestamps
  lose short intervals in the game's 32-bit Lua numbers.
- [x] Append seven read-only stock-script adapters and generate 413 exact
  loaded-object paths for 410 IDs. Missing or ambiguous owners remain unknown.
  Preserve original callback arguments, nil returns and errors. Avoid `getfenv`.
- [x] Hide collected pins in all relevant filters, recycle icons, clear selected
  reticle/footer and tracked compass target, retry failed target removal.
- [x] Preserve fast travel, native rift ownership, map/dig separation and family
  filters when every pin in a family is collected.
- [x] Build immutable packages twice and compare all bytes. Compile full Lua in
  5.1 and 5.2; test actual companion contract, shim hash pin and all DXGI exports.
- [x] Verify install, own-journal rollback, partial-copy failures, unrelated-edit
  refusal, backup corruption and exact restoration of the working baseline.

## Verification

- 160 collectible Python/Lua checks pass after the final test addition.
- 50 Raven/Nornir checks pass, including restored seal/save-boundary behavior.
- Ten bridge CTests and one capacity CTest pass; shim export checks pass.
- Current immutable package install/verify/rollback in an isolated game root
  restores all 11 targets and preserves ten other checked files.
- Installed operation: `7d93a92c6f474c4aa72bacd95d9ff94b`.
- Live startup and map/filter use succeed after fixing the `getfenv` crash.
- Live Lua state now receives 31 collected and two remaining Legendary chests;
  377 location states remain unknown. Midgard has 23 collected, two remaining
  and three unknown Legendary locations. Native and Lua counts agree. The user
  confirmed that only those few Legendary pins remain in Midgard.
- Live Legendary-filter screenshot and read-only pool counts are retained under
  `build/collectible-startup-crash/` and `build/map-open-pool-crash/`.

The game's extracted bytecode identifies Lua 5.2 with four-byte numbers.
Lua 5.1 tests provide compatibility checks; they are not the game's numeric VM.
The transport regression reproduces float32 timestamp precision loss and drives
an entire 410-state response into the generated store and map visibility layer.

## Remaining coverage and acceptance evidence

- [ ] Bind saved state for the other 377 IDs, including four Legendary chests.
  Loaded-object readers do not establish state for unloaded/despawned objects.
- [ ] Record paired before/after collection evidence for each of the seven live
  adapter families, including tracked-target cleanup with map closed.
- [ ] Record older-save/current-save switching and unloaded-area reload evidence
  for every newly promoted saved binding.
- [ ] Complete live Nornir child, native Niflheim rift and fast-travel acceptance
  across all relevant save states. Existing regression tests remain passing.

Do not hide unproved objects based on absence, regional totals or nearby objects.
The broad unloaded-save acceptance target remains open until those bindings and
paired live evidence exist. It is not implied by the 410-ID runtime contract.
