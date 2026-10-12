# Codex repository rules

Applies to the entire God of War (2018) Completionist Map source repository.

## Scope and safety

- Make feature or maintenance changes on a dedicated branch. Do not force-push, rewrite shared history or merge a cleanup branch without review.
- Keep routine housekeeping separate from gameplay, installer, catalogue and release changes. Never alter game files, generated release packages or supported-build checks as part of housekeeping.
- Preserve `archive/` and `archive/field-logs/` as historical research and runtime-validation evidence. These are intentional tracked artefacts, **not** disposable logs. Never delete, move, rewrite or add blanket ignore rules for them under a generic cleanup task.
- Keep ordinary disposable logs under an ignored `logs/` or `runtime-logs/` directory. Do not commit transient local output or credentials.

## Feature and test changes

- When changing or removing behaviour, update affected tests, active docs, catalogue contracts and release guidance in the same change. Retain historical research notes as dated historical evidence; do not retroactively rewrite old experiments.
- Never weaken, delete or replace a test merely to make the suite pass. For any test edit, explain the old assertion, new assertion and why the behaviour has legitimately changed.
- Before proposing test deletion, inventory the test's unique assertions and compare test coverage **before and after** with the same environment and test selection. Python tests primarily use `unittest`; `coverage.py` can supply line/branch measurements if available. Also inspect semantic coverage; percentages alone do not prove redundancy. If a comparable baseline is unavailable, do not delete tests automatically.
- Run the narrow relevant tests first and broader Python, Lua, PowerShell or native CTest gates where appropriate. Report exact commands, outcomes and anything not runnable. Never claim that Windows/game runtime tests passed without running them.

## Documentation and review

- Active operational documentation should identify an owner (role is sufficient) and `Last reviewed: YYYY-MM-DD`. Review it when related code or workflows change. Historical plans, dated build notes and archived evidence are exempt from retroactive metadata changes.
- Flag stale active docs for review rather than deleting them automatically. Follow `docs/MAINTENANCE.md` for the classification and safe cleanup procedure.
- For cleanup work: first inventory/propose, then review the proposed paths and impact, execute in small reversible commits, inspect the diff, and verify with tests and coverage where applicable. Never run mass deletion against `archive/`.
