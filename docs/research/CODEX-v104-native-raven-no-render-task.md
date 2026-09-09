# Codex task: explain current native Raven no-render regression

## Mission

Determine why the current v0.10.4 Raven native route re-proof can accept an Add to Compass request yet produce **no HUD compass marker and no in-world marker**, even though the earlier v0.10.3 field proof for the same authored Raven produced a real game-owned compass target with distance and an in-world marker.

This is a forensic/regression task. Do not guess from the latest installer alone. Reconstruct the exact difference between the known-good v0.10.3 runtime state and the current v0.10.4 live state.

## Branch

Work only on:

`codex/v104-raven-hud-research`

Start by pulling the branch and recording HEAD. Do not rebase or rewrite history.

## User-observed current result

After installing the current native route re-proof and selecting the same Veithurgard Raven:

- the old fake R3/L3 relative-direction HUD marker is no longer visible;
- **no native HUD compass marker appears at all**;
- **no in-world marker appears**;
- therefore this is not merely an artwork problem;
- a fresh 5-hour Codex usage window is available, so use the time for a deep comparison rather than another speculative one-line patch.

The user will run/has run the collector that writes:

`archive/field-logs/completionist-v104-native-raven-route-reproof.txt`

Treat that report as required runtime evidence when present. If it is not present yet, do not invent its contents. You may still inspect local live files read-only and prepare diagnostics, but do not claim a runtime conclusion until the report exists.

## Known-good historical proof

Read these first:

- `docs/research/v0.10.3-native-compass-live-result.md`
- `archive/field-logs/completionist-v103-native-compass-show.txt`
- `tools/v0.10.3/native-raven-production.lua`

Known-good facts from that proof:

- candidate: `Completionist_V103_Veithurgard_Raven_01`
- candidate ID: `E15E6BC82AE2773E`
- authored position around `(-64.875, 12.984375, 787.5)`
- marker type used by Lua: stock `DockPoint`
- `game.Compass.ShowMarker(candidate, DockPoint)` returned successfully
- native manager verification found the candidate
- field observation: game-owned HUD target, native distance readout (`9m` in the recorded session), and marker aligned over the in-world Raven
- the collector intentionally rolled that old proof back afterward

## Current v0.10.4 state to inspect

Read at minimum:

- `archive/field-logs/completionist-v104-native-raven-route-reproof.txt` when available
- `archive/field-logs/completionist-v104-stale-v103-native-candidate-state.json`
- `archive/field-logs/completionist-v104-raven-compass-hud-combined-offline.json`
- `archive/field-logs/completionist-v104-raven-compass-hud-four-payload.json`
- `archive/field-logs/completionist-v104-raven-compass-hud-dcb-offline.json`
- `archive/field-logs/completionist-v104-raven-compass-hud-scp-binding.json`
- `archive/field-logs/completionist-v104-packed-raven-class-runtime.txt`
- `tools/v0.10.4/install-raven-native-route-reproof.ps1`
- `tools/v0.10.4/collect-raven-native-route-reproof.ps1`
- `tools/v0.10.4/install-raven-compass-hud-runtime-candidate.ps1`
- `tools/v0.10.4/build-raven-compass-hud-dcb-offline.py`
- `tools/v0.10.4/build-raven-compass-hud-four-payload.py`
- any v0.10.3 native Raven DCB builders/installers used to create the successful tri-DCB candidate

The old stale-state report is particularly important because it already showed that later work left a mixed state:

- `mapcoords.dcb` matched the old patched v0.10.3 hash
- `compassgraph.dcb` matched the old patched v0.10.3 hash
- `mapmaster.dcb` matched neither the old stock hash nor the old patched hash
- the current mapmenu had accumulated later Raven work

Do not assume those facts are still current. Re-hash the live files read-only if the local game installation is accessible.

## Required live-state inventory

With God of War closed, inspect and record SHA256 plus relevant semantic content for the current installed versions of:

- `exec/wad/pc_le/r_ui.wad`
- `exec/wad/pc_le/wad_r_perm.dcb`
- `exec/wad/pc_le/mapmaster.dcb`
- `exec/wad/pc_le/mapcoords.dcb`
- `exec/wad/pc_le/compassgraph.dcb`
- installed `mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua`
- `mods/loader_log.txt`
- `exec/boot-options.json` and active patch-texpack entries if relevant

Also inspect ignored local manifests/backups under `build/` if present. They are evidence of what was actually installed and in what order.

Do not modify any game file during the investigation.

## Central questions

Answer these with evidence:

1. Did the current re-proof actually execute the dedicated Raven `ShowMarker` call?
   - Was candidate lookup successful?
   - Did preflight pass?
   - Did `ShowMarker` return `ok=true`?
   - Did the bridge log `request_queued=true`?
   - Did `FindMarkersByIconClass(...)` later report the candidate as manager-owned?

2. If the manager says the candidate is active but nothing renders, what changed since the known-good v0.10.3 session?

3. Is the authored native Raven record still byte/field equivalent to the known-good v0.10.3 candidate in all fields that matter to compass rendering?
   - mapmaster identity/flags/state/WAD association
   - mapcoords identity/coordinates
   - compassgraph membership/edge data
   - any dependency/index/table accounting

4. Did later map-icon work mutate `mapmaster.dcb` in a way that kept `GetMarkerInfo` working but broke native compass/in-world presentation?

5. Did later `wad_r_perm.dcb` work alter the stock `DockPoint` CompassIconClass behavior, UID ordering, class lookup, `IconName`, `RadiusIconName`, `InWorld_tMPIcon_Name`, or any neighboring table/accounting in a way not captured by the earlier byte-local assertions?
   - Do not merely trust “DockPoint record byte-identical”; validate the complete lookup context and table/order assumptions.

6. Did the current `r_ui.wad` full-group Raven HUD insertion alter resource accounting, type bases, heap indices, or lookup behavior affecting the stock `goboatdock` / `goProtoBoatDock` / `MDL_boatdock` chain?
   - Verify the stock DockPoint HUD chain resolves in the current WAD, not just that its source bytes survived.

7. Is manager verification a false-positive for visual readiness?
   - Determine exactly what `FindMarkersByIconClass(enabledShowOnCompassMarkerFlags)` proves and what it does not prove.
   - A marker being returned from the manager is not sufficient if renderer/world-marker resources fail later.

8. Is the no-render result caused by the current mixed installation rather than the re-proof Lua bridge itself?

## Strong comparison requirement

Build a machine-readable comparison between:

A. the exact historical v0.10.3 successful candidate state that can be reconstructed from archived manifests/builders/reports, and

B. the current live v0.10.4 state.

For each relevant file/resource, classify it as:

- exact known-good equivalent
- intentionally changed but proven unrelated
- changed and plausibly causal
- unknown/unrecoverable

Do not settle for top-level file hashes when parsers/builders can compare semantic records.

## Preferred experimental strategy

Do **offline/read-only** work first.

If a causal difference is isolated, build the smallest reversible candidate needed to test it. Prefer a surgical A/B restore of one known-good subsystem over stacking new features.

Examples of useful controls, only if evidence supports them:

- recreate the exact v0.10.3 successful tri-DCB native candidate on top of the current map artwork while leaving the new Raven HUD WAD/DCB disabled;
- temporarily restore stock `r_ui.wad` + the historically proven packed `wad_r_perm.dcb` while keeping the native Raven tri-DCBs, to test whether the no-render regression lives in HUD resource/class work;
- restore only the known-good native `mapmaster.dcb` candidate if semantic comparison proves later mapmaster changes are the differentiator.

Do not run God of War yourself. Produce a fail-closed installer/rollback pair and an explicit observation checklist for the user.

## Safety constraints

- God of War must remain closed during file analysis/build/install scripting.
- Never modify save files, progression, collectible state, or marker completion state.
- Preserve the currently working Raven map artwork.
- Preserve backups of every live file before any future runtime A/B install.
- Never overwrite a live file whose hash does not match the exact source state validated by the candidate builder.
- Do not delete stale `active.json` manifests merely to make an installer proceed; reconcile them with hashes and backups.
- Do not weaken a validation gate just to get a test running.
- Generated/proprietary candidate binaries remain under ignored `build/` paths and must not be committed.
- Reports, tools, and research notes may be committed.

## Deliverables

Commit all useful source/report changes to `codex/v104-raven-hud-research` and push them.

At minimum produce:

1. `docs/research/v104-native-raven-no-render-regression.md`
   - concise root-cause analysis
   - exact known-good vs current differences
   - confidence level
   - what the current runtime log proves

2. A read-only comparison/diagnostic tool under `tools/v0.10.4/` that can reproduce the important comparison on David's machine.

3. An archived machine-readable report under `archive/field-logs/` after the user/local runner executes it, or a runner that will create that report safely.

4. If and only if evidence identifies a specific causal subsystem, a reversible runtime A/B installer plus rollback that changes the minimum possible files.

5. A short final note stating exactly one of:
   - `ROOT_CAUSE_PROVEN`
   - `ROOT_CAUSE_NARROWED_NOT_PROVEN`
   - `EVIDENCE_INSUFFICIENT`

If `ROOT_CAUSE_PROVEN`, state the exact next runtime test and expected result.

## Important: do not spend the window re-solving the custom Raven artwork

The custom Raven map art works. The dedicated Raven HUD resource chain has already been built and validated offline. The current blocker is that the known-good native marker presentation regressed to **no visual at all**. Focus the five-hour window on identifying the regression between the known-good native state and the current mixed v0.10.4 state.
