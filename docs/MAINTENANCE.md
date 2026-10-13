# Repository maintenance policy

Owner: Completionist Map maintainer
Last reviewed: 2026-10-12

## Initial inventory (main, 2026-10-12)

- Approximately 3,608 tracked files, of which approximately 2,349 files / 466 MB live in `archive/`.
- `archive/field-logs/` and `archive/field-logs/runtime-captures/` contain intentional reverse-engineering and regression evidence. Some native test fixtures directly reference archived captures.
- The existing `.gitignore` already excludes `*.log`, local builds and packaged ZIPs. Large archived `.txt` and `.json` captures are **not** the same thing as disposable local logs.
- Active source: `native/`, `tools/`, `config/`, `catalogue/`, `assets/`. Documentation: `README.md`, `CHANGELOG.md`, `NEXT_STEPS.md` and `docs/`. The dated `docs/research/`, `docs/builds/` and `docs/superpowers/` files record history and may reflect earlier implementations.

No evidence was removed by this policy change.

## Change-by-change maintenance

1. **Inventory and propose:** list candidate files, current code references, active consumers, unique assertions and whether each item is generated output or historical evidence. Identify docs referencing touched code.
2. **Review:** present the exact proposed deletion or rewrite before executing it. Do not assume that dated or unmodified material is redundant.
3. **Small branch-only edits:** separate documentation, test and housekeeping changes from production features when practical. Never force-push or alter published Git history.
4. **Verify:** review `git diff --check`, `git diff --stat` and the full diff; run targeted tests and compare coverage when tests are removed. Record commands, results and limitations in the PR. Merge only after review.

## Tests and coverage

Many Python suites use `unittest`, not pytest. For example, from the repository root:

```powershell
python -m unittest discover -s tools/v0.10.5 -p "test_collectible_runtime_model.py"
```

If `coverage.py` is installed, compare the same test selection **before and after** a proposed removal:

```powershell
python -m coverage run --branch --source=tools/v0.10.5 -m unittest discover -s tools/v0.10.5 -p "test_collectible_runtime_model.py"
python -m coverage report -m
```

These are example commands, not evidence of a successful run. Native tests additionally require a configured Windows/MSVC build and CTest; Lua and PowerShell checks have their own toolchain requirements. Where a comparable baseline cannot be generated, retain the tests and document the verification gap.

## Documentation lifecycle

- **Active operational guidance:** assign a maintainer/owner role and review date when creating or materially editing it. Re-review whenever the implementation or installer it describes changes. Maintain a single source of truth for current release behaviour.
- **Historical research, field evidence and dated plans:** keep as historical records. Link to current behaviour rather than silently rewriting old findings.
- **Monthly or before a release:** inspect active docs not reviewed since relevant code changed; propose precise edits, archive/status labels or cross-links. Do not automatically delete them.

## Local log retention

- Write disposable debug/run logs under ignored `logs/` or `runtime-logs/`. Their retention target is **30 days**, subject to explicit manual review and a local backup if needed.
- Review local log sizes periodically; delete only confirmed disposable files older than 30 days. Do not use generic recursive cleanup against the repository and do not delete files in `archive/`, runtime captures, test fixtures, release records or saved-game evidence.
- Files already tracked remain tracked even if their extensions match `.gitignore`. A future archive migration requires a separate inventory, consumer audit, storage proposal and explicit approval.
