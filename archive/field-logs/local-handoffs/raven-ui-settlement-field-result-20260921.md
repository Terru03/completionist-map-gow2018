# Raven UI settlement field result — 2026-09-21

Manual field result after the UI-polish proof refresh:

- authoritative old-save Raven filtering still worked;
- Raven title/subtitle polish was under live retest;
- two compass/UI regressions remained.

Observed regressions:

1. The bottom-row ShowOnCompass action text did not update immediately in every tested add/replace/remove instance.
2. Sequence: add a Raven, then remove that same Raven.
   - the custom Raven target disappeared;
   - a boat/stock-looking marker then appeared on the compass HUD.
3. Sequence: add one Raven, then replace it with another target/Raven.
   - this did not exhibit the boat-marker problem.

Diagnosis against the proven v0.10.4 v3.3 implementation:

- v0.10.5 had retained an immediate one-shot prompt refresh, but lost the v3.3 MapOn.Update settlement/watchdog path that reasserted the cursor/footer text after the native compass manager settled;
- v0.10.5 also lost v3.3's suppression of the legacy CompletionistMapV100Target Raven HUD route while the native custom Raven compass class owns tracking;
- the add -> remove symptom is consistent with the custom target disappearing and the old legacy Raven HUD route becoming visible again.

Fix chain started from this field result:

- `02b944b` — restore asynchronous prompt settlement and legacy Raven HUD suppression in the generalised 53-Raven runtime;
- `3ca2f16` — regression coverage for one-frame base UI overwrite plus same-Raven add -> remove legacy HUD reactivation;
- temporary CI workflow added afterwards to validate Lua/model tests and safety tokens.

Scope remains UI/compass only. Do not change persistence/native Raven authority, save data, progression, or process memory.


## Validation and next boundary

The exact direct same-Raven sequence is now covered:

- Add Raven A;
- allow one stock/base update that overwrites the UI;
- settlement restores the footer/cursor prompt to Remove;
- Remove Raven A;
- simulate legacy Raven HUD reactivation plus one stale base update;
- settlement leaves custom targets = 0, stock targets = 0, legacy Raven HUD inactive;
- cursor/footer prompt returns to Add.

Validation:
- temporary GitHub Actions run `35627933908`: success;
- exact direct Add A -> Remove A run `35628065149`: success;
- temporary CI workflow removed in `aac6ad2`.

Live runner prompts now explicitly accept `REGRESSION` so a failed manual observation goes through the normal catch/archive/push path instead of requiring Ctrl+C. Commit: `664e46d`.

Before the next live test, refresh the generated mapmenu proof because `all-ravens-map-runtime.lua` changed in `02b944b`.


## Second live regression set — same map-open re-add + checkpoint reload

Field observations:

1. Same map-open compass sequence:
   - add Raven A;
   - remove Raven A;
   - add Raven A again without closing the map;
   - a stock/boat-looking HUD compass marker appears on the third action.

2. Persistence/reload sequence:
   - kill a live Raven;
   - reload the checkpoint/save point corresponding to after that kill;
   - reopen map;
   - that Raven was forced visible instead of remaining absent.

The latest manual run did not create a new pushed proof commit, so these observations are recorded here from the field report.

### Root cause: same-map re-add

The previous settlement fix considered Raven removal complete once the custom CompletionistRaven target disappeared. It did not retain explicit custom-Raven ownership over the compass target for the remainder of the Raven interaction. A legacy/stock target could therefore reactivate between Remove and the next Add.

Fix `67fc1f0`:
- adds persistent `customCompassOwnsTarget` for Raven-origin compass actions;
- while owned, `MapOn.Update` suppresses the legacy Raven HUD route and removes stock targets;
- Remove adds an immediate stock-target guard;
- re-Add adds another immediate post-show stock-target guard;
- stock/delegated actions explicitly release custom ownership.

Regression in `6b1a8fb` deliberately injects a fake `boat` stock target on the exact third-click Add and requires it to be removed immediately and after the following base update.

### Root cause: checkpoint authority

The native bridge increments snapshot generation only when the complete 53-Raven state changes. Reloading the same post-kill checkpoint may therefore legitimately return the same generation.

Before the fix:
- `CompletionistMapV105ResetRavenStates` cleared Lua state;
- `refreshNativeAuthority` rejected `generation <= lastNativeGeneration`;
- the equal-generation authoritative checkpoint snapshot was therefore discarded;
- unknown/catalogue-default-visible fallback could make the Raven visible again.

Fix `67fc1f0`:
- after explicit save/checkpoint reset, permit the equal native generation exactly once;
- normal map close/reopen still rejects equal generations, preserving immediate-event state;
- after reset, perform a bounded 180-frame native refresh window to accept a newer snapshot if a different save/checkpoint is still settling.

Fix `116c3aa`:
- `OnRestoreCheckpoint` republishes the exact loaded Raven's read-only `ravenKilled` field immediately and for a bounded 20 x 0.1 s settle window;
- no progression/save/process-memory writes are introduced.

Regression coverage:
- same-generation authoritative reapply after reset;
- newer generation during bounded reset window;
- loaded Raven field settling after `OnRestoreCheckpoint`;
- Add A -> Remove A -> Add A in one map-open session with injected boat/stock fallback.

Live proof `82862a4` now explicitly requires:
- immediate kill disappearance;
- close/reopen remains absent;
- reload the checkpoint created after the kill;
- reopen map;
- exact Raven remains absent;
- result records `checkpoint_reload_after_kill_manual=true`.

The generated-candidate refresher now safely refreshes both generated Lua files (mapmenu + precisionchallenge) while freezing the three binary candidate pins.
