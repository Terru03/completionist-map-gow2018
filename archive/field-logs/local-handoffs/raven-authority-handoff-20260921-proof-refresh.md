# Raven release-candidate handoff addendum — 2026-09-21 proof refresh

## State entering this addendum

The authoritative 53-Raven persistence path is already field-proven on the advanced save:

- 27 killed Ravens were absent;
- 26 live Ravens remained;
- no save/progression/process-memory writes were introduced.

The Raven UI polish fix is already on the release-candidate branch:

- title: `Odin's Raven`;
- subtitle: `Completionist Map`;
- immediate Add/Replace/Remove compass prompt refresh.

Relevant implementation/test chain:

- `f4899d9` — restore Raven reticle and live compass prompt;
- `2cdb7f5` — regression coverage;
- `fa2feea` — CI validation;
- `b72fc33` — remove temporary CI gate;
- `6212a8b` — UI polish handoff.

The earlier live snapshot proof was preserved after rebase as:

- `2b7192c` — `test(v0.10.5): capture Raven snapshot delivery proof 20260921-155801`.

That archived run is not final UI acceptance. It stopped at the advanced-save manual confirmation and rolled back exactly.

## Stale proof pin discovered

After the UI runtime changed, `prepare-all-ravens-delivery-candidate.py` correctly rejected the generated map hook because:

```text
ValueError: rendered delivery candidate differs from pinned proof
```

The stale field is:

```text
archive/all-ravens/all-ravens-release-candidate-offline.json
files["mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua"]
```

The proof still pinned the pre-UI-fix mapmenu SHA.

A full five-file rebuild from the live game directory was attempted and correctly rejected:

```text
ValueError: source differs from runtime-proven v3.3: exec/dc/pc_le/mapmaster.dcb
```

Do not solve this by rebuilding the binary candidate from the user's current game root. The current game installation is not guaranteed to equal the exact runtime-proven v3.3 source fixture.

## Correct repair

Only the generated `mapmenu.lua` hook needs refreshing.

`prepare-all-ravens-delivery-candidate.py` now supports:

```text
--refresh-proof
```

The mode:

1. validates the existing five-file candidate set;
2. validates every non-map candidate file against its pinned proof;
3. verifies the existing map candidate base still hashes to the runtime-proven source map Lua;
4. renders the current 53-Raven map runtime hook;
5. accepts only a current map candidate that matches either the previous pin or the newly rendered runtime;
6. rewrites only the generated map candidate and its `sha256/bytes` proof entry;
7. leaves all binary candidate pins unchanged;
8. can then be verified again with `--check`.

Implementation commit:

- `44d028c` — `build(v0.10.5): support safe Raven proof refresh`.

## Self-pushing failure evidence

The user explicitly wants local test failures archived to Git so the next analysis can inspect them directly without manually pasting console output.

New helper:

```text
tools/v0.10.5/refresh-raven-delivery-proof-and-push.ps1
```

It archives and pushes both success and failure evidence under:

```text
archive/field-logs/runtime-captures/raven-delivery-proof-refresh-<UTC stamp>/
```

Relevant commits:

- `2d965b4` — add self-pushing proof refresh;
- `969ad9d` — make staged commit paths explicit.

A live-proof outer capture wrapper was also added:

```text
tools/v0.10.5/run-raven-native-snapshot-delivery-live-proof-captured-and-push.ps1
```

Its purpose is to catch failures that occur before the existing live runner creates its own capture directory. If the inner runner already committed a failure, the wrapper does not duplicate it.

Commit:

- `255e9c2` — capture early Raven live-proof failures.

## Next action

1. Pull the latest `codex/all-ravens-release-candidate`.
2. Run `refresh-raven-delivery-proof-and-push.ps1`.
3. Inspect the pushed proof-refresh result.
4. If green, run the captured live-proof wrapper.
5. Complete manual acceptance:
   - advanced save: 26 live / 27 absent;
   - `Odin's Raven` + `Completionist Map`;
   - immediate compass prompt transitions;
   - immediate killed-Raven disappearance;
   - map reopen persistence;
   - fresh save: all 53 Ravens;
   - exact rollback.

Do not reopen GameObject codec, authority discovery, DXGI/XInput transport, or save-side research unless a new field failure specifically points there.
