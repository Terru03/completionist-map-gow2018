# Raven release audit findings

Audit branch: `codex/raven-release-adversarial-audit`

Initial audit baseline: `5f0f593`

Final green audit head before workflow removal: `2434c10324914d967f4ac1d87784d7be23afbc2d`

Final validation run: `35686252748` — **success**

The release-candidate branch was not modified during the audit.

## A01 — release-blocking: compass intent and UI settlement races

Paths:

- `tools/v0.10.5/all-ravens-map-runtime.lua`
- `tools/v0.10.5/test_all_ravens_lua.py`

Deterministic regressions reproduced:

1. Add Raven A -> delayed native hide -> Remove A -> Add A before settlement: stale custom IDs could make the latest Add behave as Remove.
2. A late base `MapOn.Update` could overwrite the settled Raven footer/cursor prompt.
3. Hover Raven B while Raven A settlement remained pending: A's prompt could overwrite B's prompt.
4. Kill tracked Raven A and then expose a legitimate stock target: stale Raven ownership could suppress the stock target.
5. Cross a load boundary with stale Raven selection: stale selection could swallow the next stock compass action.

Fix:

- latest explicit user intent is authoritative during settlement;
- pending Add reasserts the custom Raven target if a delayed hide removes it;
- prompt settlement follows the Raven currently under the cursor, not stale action state;
- settled Remove releases stock ownership;
- kill/load-boundary transitions clear stale compass ownership and selection.

Evidence:

- archived red/green Lua evidence under
  `archive/field-logs/runtime-captures/raven-release-adversarial-audit-20260921/`;
- final Lua suite: **26 tests passed**.

Live retest remains required because these paths interact with the real game compass manager.

## A02 — release-blocking: generation alone did not prove post-load Raven authority

Paths:

- `native/raven-authority-bridge/src/authority_runtime.cpp`
- `native/raven-authority-bridge/src/authority_runtime.h`
- `native/raven-authority-bridge/src/snapshot_delivery.cpp`
- `native/raven-authority-bridge/src/snapshot_delivery.h`
- `tools/v0.10.5/all-ravens-map-runtime.lua`
- `tools/v0.10.5/raven_runtime_model.py`
- associated Lua/model/native/build/runner tests.

Failure sequence:

1. Raven state A is captured before a save/checkpoint load.
2. Lua observes a load boundary.
3. The staged native source can remain temporarily old while loading settles.
4. The periodic native worker captures the still-old source after the boundary and assigns it a numerically newer generation.
5. The previous design treated that newer generation as post-boundary authority even though it could still semantically describe the old save.

This invalidated the assumption that capture generation by itself proves restored-save freshness.

Fix: epoch-bound **V2 boundary capture**.

Normal map-open reads still use:

```text
GET RAVEN_SNAPSHOT_V1
```

A save/checkpoint boundary now owns a monotonically increasing Lua boundary epoch. After the load is known to be complete, Lua requests:

```text
CAPTURE RAVEN_SNAPSHOT_V2 boundaryEpoch=<N>
```

The native bridge performs a fresh read/decode in response to that request and echoes the same epoch in:

```text
RAVEN_SNAPSHOT_V2 schema=2 boundaryEpoch=<N> ...
```

While a boundary is pending:

- periodic V1 snapshots cannot settle it, regardless of generation;
- mismatched/stale V2 boundary epochs are rejected;
- only a complete 53-Raven V2 capture carrying the current epoch may replace the retained last-good/session-kill state.

Load arming was also tightened:

- loading-start events disarm Raven authority;
- `EVT_LoadSaveFile_Done` arms the boundary capture only after completion;
- `OnRestoreCheckpoint` arms it after the wrapped restore call returns.

This remains read-only with respect to game/save/progression state. The native path reads the same staged source and does not write process memory or progression.

Evidence:

- deterministic stale-periodic regression added first;
- native boundary wire response test;
- pure runtime-model epoch tests;
- live-proof parser requires matching boundary epochs and V2-only fresh authority;
- final native CTest: **5/5 passed**.

## A03 — release-blocking: candidate proof refresh was not fully transactional

Paths:

- `tools/v0.10.5/prepare-all-ravens-delivery-candidate.py`
- `tools/v0.10.5/refresh-raven-delivery-proof-and-push.ps1`
- `tools/v0.10.5/test_raven_delivery_prepare_transaction.py`
- `tools/v0.10.5/test-raven-delivery-proof-refresh-wrapper.ps1`

Audit reproduced failure paths where proof refresh could leave:

- one generated Lua payload updated while another write failed;
- staged proof JSON after a later commit/publish failure;
- index/worktree state that was not identical to pre-run state;
- insufficient five-file validation around the refresh transaction.

Fix:

- Python candidate preparation now stages generated outputs transactionally and rolls all candidate/proof writes back on failure;
- wrapper records pre-run Git/index/worktree state;
- failed check/commit paths restore the candidate/proof transaction and staging state;
- failed evidence publication cannot strand staged evidence;
- push failure intentionally preserves the already-created local proof commit instead of destroying successful work;
- failure evidence remains separately archiveable/publishable.

Final wrapper evidence:

```text
RAVEN_PROOF_REFRESH_WRAPPER_TESTS_PASSED
rollback_after_check_failure=true
blocked_commit_cleanup=true
push_failure_commit_preserved=true
```

## A04 — high: five-file rollback interruption recovery lacked portable proof

Path:

- `tools/v0.10.4/nornir-runtime-candidate3.ps1`
- `tools/v0.10.5/test-raven-transaction-resume-synthetic.ps1`
- `tools/v0.10.5/test-all-ravens-transaction.ps1`

The transaction engine already persisted per-entry `write_state=restored`, but the release gates only proved install interruption recovery, not interruption during rollback itself.

No engine defect was found. A fixture-independent synthetic five-file test was added to prove:

1. install candidate over five files;
2. interrupt rollback after one restored write;
3. reopen the persisted transaction;
4. resume rollback;
5. restore all five files byte-for-byte.

Evidence:

```text
RAVEN_SYNTHETIC_ROLLBACK_RESUME_PASSED
files=5 interruption=true resumed=true exact=true
```

## A05 — release-blocking: owned DXGI DLL + manifest rollback was not interruption-safe

Paths:

- `tools/v0.10.5/install-raven-authority-bridge.ps1`
- `tools/v0.10.5/rollback-raven-authority-bridge.ps1`
- `tools/v0.10.5/recover-raven-authority-bridge-startup.ps1`
- `tools/v0.10.5/raven-authority-bridge-operation.ps1`
- bridge install/operation tests.

Failure sequence:

1. an older owned bridge layer exists;
2. rollback restores the previous `dxgi.dll`;
3. process terminates before the previous manifest is restored;
4. next startup sees old DLL + newer manifest;
5. old recovery path refuses the mismatched pair and cannot finish rollback.

Fix:

- create an owned operation journal before the first destructive DLL/manifest write;
- journal exact operation SHA and exact previous owned backup pair;
- install/rollback update operation phase as writes complete;
- startup recovery processes an unfinished journal before normal manifest-chain recovery;
- recovery accepts only the operation SHA or exact previous owned SHA;
- previous backup paths must remain under the Completionist-owned backup directory;
- foreign/unknown DLL or ambiguous manifest state remains fail-closed;
- successful install/rollback/recovery must leave no operation journal.

Synthetic midpoint/refusal evidence:

```text
RAVEN_BRIDGE_OPERATION_SYNTHETIC_PASSED
mixed_pair=true
missing_target=true
absent_pair=true
unknown_dll_refused=true
unknown_manifest_refused=true
backup_scope_refused=true
```

The final live proof also fails if the operation journal remains after rollback.

## Final offline verification

GitHub Actions run:

```text
35686252748
head=2434c10324914d967f4ac1d87784d7be23afbc2d
conclusion=success
```

Verified:

```text
Lua integration:                 26 passed
Pure runtime model:              25 passed
Candidate/template contract:     15 passed
Transactional prepare tests:      4 passed
Proof-refresh wrapper:            passed
Native/live proof parser:         passed
Five-file rollback resume:        passed
DXGI journal synthetic recovery:  passed
PowerShell parser:                7 files passed
Native bridge CTest:              5/5 passed
Safety scan:                      findings=0
```

Security/safety invariants retained:

- no save writes;
- no progression/quest writes;
- no process-memory writes;
- no static native descriptor writes;
- loopback-only native transport;
- unknown/foreign DXGI state remains fail-closed.

## Proof-refresh scope

The release proof contract continues to freeze the three binary candidate pins. Refreshable release data is restricted to the generated Raven Lua payloads plus authority/proof metadata. Transactional failure tests now protect candidate/proof worktree and staging state.

## Remaining release requirement

Offline audit is complete, but the changed runtime/native boundary and compass paths require one final real-game acceptance pass after clean integration onto the Raven release-candidate branch.

That live pass must prove at minimum:

1. advanced save: exact surviving Raven set;
2. title `Odin's Raven` and subtitle `Completionist Map`;
3. same Raven Add -> Remove -> Add retains Raven HUD target with no boat/stock fallback;
4. immediate kill removes exact Raven;
5. same-session map reopen keeps it absent;
6. checkpoint/save reload logs an authority boundary epoch and accepts only a matching V2 boundary capture;
7. post-load Raven set reconstructs correctly;
8. genuine fresh save shows all 53;
9. exact five-file + native bridge rollback;
10. no Raven bridge operation journal remains.

## Integration recommendation

The audit changes are suitable for clean integration, but the audit branch itself should **not** be merged wholesale because it contains temporary CI, audit plans, and red/green evidence artifacts.

Create an integration branch from the current `codex/all-ravens-release-candidate` tip and carry only:

- production/runtime/native fixes;
- permanent regression tests;
- permanent release/proof/rollback gates.

Exclude:

- `.github/workflows/raven-audit-validation.yml`;
- `docs/superpowers/plans/2026-09-21-raven-release-audit.md`;
- `archive/field-logs/local-handoffs/astra-high-raven-release-audit-20260921.md`;
- this audit-only findings file from the release payload if a clean RC handoff already records the result;
- audit-only red/green runtime-capture files.

Do not consider Ravens release-complete until the final live pass succeeds.
