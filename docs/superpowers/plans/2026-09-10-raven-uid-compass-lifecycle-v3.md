# Raven lifecycle v3 implementation plan

Goal: clear completed real target during gameplay; keep Twin tied to map view.
Architecture: keep v2 UID and binary route. Append read-only observer to production precisionchallenge callbacks; append map lifecycle wrappers. Package five pinned files with same transaction engine.
Tech: Lua 5.1, Python unittest/lupa, PowerShell.

- [x] Read v2 human result, proof, source and prior Raven callback logs. No crash; loader log absent.
- [x] Create requested branch at 934015b68955b2a5449d35665a194493fdfd1171.
- [ ] Add failing Lua tests: closed/open map completion, Twin/stock/no target, save reload, target eligibility; map destroy vs teardown, repeated opens and failures.
- [ ] Keep exact object and UID routing. Replace missing global oracle lookup with lexical read-only oracle using authoritative lifecycle boolean. Cache only local observations; retry failed cleanup.
- [ ] Append precisionchallenge bridge after native OnHitByWeapon, OnRestoreCheckpoint, OnStart. Read ravenKilled and existing target predicate; protected notification only. Preserve native function bodies byte for byte.
- [ ] Remove Twin wrapper around production destroy. Cleanup on MapOn.SubmenuExit, Exit and ClearIcons; idempotent references; no duplicate object on repeated create.
- [ ] Build separate lifecycle-v3 Python builder/proof, five-file runtime wrapper and transaction tests. Pin source blobs and all output hashes. Keep frozen baseline refusal and inherited write guards.
- [ ] Run Lua regression, Python relevant Raven suites, two builds/check, transaction fixture tests. Archive fresh evidence separately.
- [ ] Independent review; fix findings, rerun checks, commit and push v3 only.
- [ ] Write complete handoff with commands, test matrix and unresolved runtime limits.

Test command: py -3 -m unittest discover -s tools/v0.10.4 -p 'test_raven*lua.py' -v
Build command: py -3 tools/v0.10.4/build-raven-uid-compass-lifecycle-v3.py --raven-root build/v0.10.4-raven-uid-compass-lifecycle-v3/source/game-root
Transaction command: powershell -NoProfile -File tools/v0.10.4/test-raven-uid-compass-lifecycle-v3-transaction.ps1

Source fixture: frozen v2 transaction backups for four map files; read-only copy of pinned production r_ui.wad and precisionchallenge.lua. No writes to game root or saves. Runtime installer still requires frozen production baseline; human must roll v2 back using v2 branch before v3 install.
