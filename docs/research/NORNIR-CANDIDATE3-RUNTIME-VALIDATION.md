# Nornir Candidate 3 controlled runtime validation

## State

Candidate 3 remains **offline-only**. The reusable collectible framework and Candidate 3 offline proof are committed, but Candidate 3 has not been installed or runtime-tested.

Pinned Candidate 3 WAD:

`90391a2841d3a9ad889b95d5c17fc0ee09de803a57675b6d237a98051b08c660`

Candidate 2 remains permanently retired and is not an input to Candidate 3.

## Why this installer exists

The next useful evidence is a tightly controlled field test of Candidate 3. The installer follows the already-proven Raven/Candidate 2 transaction pattern but is stricter in several places:

- exact ten-file Candidate 3 proof validation before installation;
- exact Candidate 3 WAD identity and donor material `+0x20` rule validation;
- explicit rejection of the retired Candidate 2 WAD;
- frozen Raven verification before backup and again after backup immediately before the first runtime write;
- all destination backups and backup SHA checks complete before the first game write;
- all required backup SHA checks complete again before the first rollback write;
- durable per-entry `pending` / `write-started` / `installed` / `restored` transaction state;
- source SHA check before each write;
- temporary-file copy plus SHA verification before destination replacement;
- post-install SHA verification for all ten files;
- automatic full rollback on any partial installation failure;
- normal rollback refuses files changed after installation unless `-ForceRollback` is explicitly chosen after review;
- forced rollback rejects terminal/unknown transactions and never deletes an uncertain non-Candidate 3 file from a `write-started` entry;
- exact pre-install state restoration, including removal of destinations that did not exist before installation;
- exact active and transaction-local manifest, transaction-root, file-set, path-topology, and reparse-point validation before install/recovery decisions;
- `GoW.exe` identity check under the selected game root before install or rollback;
- branch, HEAD, tracked-tree, and game-process checks repeated at the final pre-write gate and before each game-file write;
- frozen Raven verification after rollback;
- no save, progression, or marker-state writes;
- no automatic God of War launch.

`Install` is intentionally disarmed unless the caller also supplies `-ConfirmRuntimeTest`.

## Offline transaction gate

Run this before any field install:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\v0.10.4\run-nornir-runtime-candidate3-installer-offline.ps1"
```

The gate does **not** write to the installed game. It:

1. parses the installer and self-test with the PowerShell parser;
2. checks the archived Candidate 3 proof and current build output remain exact, offline-only, and pinned;
3. runs the exact transaction helpers against a temporary fake game root;
4. proves successful install + exact rollback;
5. injects failures before the manifest, before the first write, and after a partial install;
6. proves a corrupt backup stops rollback before any destination changes;
7. proves pending destinations survive recovery and uncertain non-Candidate 3 files survive forced recovery;
8. proves stale/unknown force status, malformed manifest roots/file sets, overlapping roots, and reparse points fail closed;
9. proves a tampered installed file blocks normal rollback;
10. proves explicit forced rollback can restore the exact baseline after review.

Expected final marker:

`NORNIR_RUNTIME_CANDIDATE3_INSTALLER_OFFLINE_GATE_PASSED`

Passing this gate does not itself make Candidate 3 runtime-proven.

## Status

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\v0.10.4\nornir-runtime-candidate3.ps1" -Mode Status
```

## Controlled field install

Do not perform this until the offline gate output has been reviewed.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\v0.10.4\nornir-runtime-candidate3.ps1" -Mode Install -ConfirmRuntimeTest
```

The installer does not launch the game. After a successful install, launch God of War manually and test only the planned visual slice first:

1. Raven remains visible and unchanged.
2. Stock boat/dock markers remain stock and do not show Nornir art.
3. Opening the map does not crash.
4. Nornir map marker renders the custom Nornir art.
5. Selecting/tracking Nornir shows the custom compass HUD art.
6. Approaching/tracking Nornir shows the custom in-world art.
7. Raven Add/Replace/Remove semantics still behave correctly.

Do **not** test Nornir completion/opening lifecycle until the visual/resource slice survives map + compass + in-world validation.

## Rollback

Close God of War first, then:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\v0.10.4\nornir-runtime-candidate3.ps1" -Mode Rollback
```

Normal rollback refuses to overwrite a destination that no longer matches the installed Candidate 3 SHA. `-ForceRollback` exists only for reviewed recovery and should not be used reflexively. It cannot replay a terminal or unknown transaction, and it will not delete unknown bytes from an entry whose write never reached the durable `installed` state.

A successful rollback must end with frozen Raven production verification passing.

## Evidence to archive after the field test

Record at minimum:

- installer transaction ID;
- exact Git HEAD;
- Candidate 3 WAD SHA;
- map-open result;
- Raven visible/unchanged result;
- stock boat/dock marker result;
- Nornir map art result;
- Nornir compass HUD result;
- Nornir in-world result;
- crash/no-crash result;
- rollback result and Raven verifier result.

Only after those visual checks pass should Candidate 3 move on to its already-designed Nornir lifecycle/opening validation.
