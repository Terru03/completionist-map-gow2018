# All-Ravens runtime run-artifact policy

Status: mandatory for v0.10.5 Raven field/install work.

Every invocation of `tools/v0.10.5/install-all-ravens-working-mod.ps1` on the
research branch must preserve enough evidence to reconstruct both successful
and failed runs.

## Required per-run archive

The run directory is:

`archive/field-logs/runtime/all-ravens-working-install-<UTC run id>/`

Whenever the corresponding source exists during the run, the archive contains:

- `run.txt` — full PowerShell transcript, including nested build, rollback,
  install and Git output.
- `result.json` — machine-readable final outcome and error summary.
- `error.txt` — full exception text for failed runs.
- `git-state.txt` — branch, HEAD and working-tree state at start and before
  the artifact commit.
- `active-transaction-before.json` — active Raven transaction snapshot before
  the run changes it.
- `active-transaction-after.json` — active transaction snapshot after the
  run, including rolled-back or installed state.
- `candidate-proof-used.json` — exact tracked candidate proof present at the
  end of the run.
- `candidate-files.json` — exact SHA-256 and byte size of every generated
  candidate file.

The run directory is committed for both `installed` and `failed` outcomes.
The publisher retries GitHub push three times. If a GitHub/network failure
prevents an immediate push, the run commit remains on the local research branch
and must be pushed with the branch before further field work is considered
fully archived.

## Candidate proof

A changed `archive/all-ravens/all-ravens-release-candidate-offline.json` is
committed and pushed before runtime installation. If that proof push fails,
the install run fails closed. Its subsequent run-artifact commit is a child of
the local proof commit, so a later successful branch push publishes both.

## Upgrade transaction rule

A non-terminal active transaction is always validated strictly against its own
candidate hashes before rollback or mutation.

A terminal transaction (`rolled-back` or
`rolled-back-after-install-failure`) is historical evidence. During a
candidate upgrade it is validated for candidate family, branch, transaction
identity, game root and entry count, but its old candidate SHA values are not
compared against the replacement candidate. The new transaction replaces
`active.json` only when the guarded new install begins.

This distinction fixes the 2026-09-18 failure
`Candidate 3 transaction SHA changed: mapmenu`: the previous candidate had
already been restored correctly, and only its historical mapmenu SHA differed
from the newly rebuilt candidate.

## Safety

Run archiving and runtime bootstrap must not write God of War save data or
progression state. Runtime candidate installation remains limited to the five
approved game files and retains transaction backups before the first game-file
write.


## Outer recovery launcher

Field runs should be started through:

`tools/v0.10.5/run-all-ravens-working-mod.ps1`

The launcher is intentionally separate from the installer. Before launching the
installer it scans for unpublished `all-ravens-working-install-*` directories
and commits/pushes them. It parses the installer before execution, runs the
installer in a child PowerShell process, then rescans for orphaned run evidence
after any child failure. Finally it writes and pushes its own independent
`all-ravens-launcher-<UTC run id>` record.

This outer layer exists specifically for failures where the installer itself
cannot reach its internal artifact publisher. A field failure is therefore
expected to leave either the normal installer run archive, the outer launcher
archive, or both.
