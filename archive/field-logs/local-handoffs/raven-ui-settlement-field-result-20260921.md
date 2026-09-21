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
