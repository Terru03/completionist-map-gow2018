# Shared-Loader Twin plan

Goal: test two marker UIDs with same proven Raven resource. No real install.

Audit first: inspect all marker fields, native repeated pairs, Stage A/A2,
state gates, and pool checkout. Evidence saved by `audit-raven-shared-loader.py`.

Plan from audit:

- Keep frozen Raven and all native records. Append Twin UID and 32 m coordinate.
- Use same loader text/hash. Keep all opaque fields and `InitState=0`.
- Pool checkout caps live objects at authored capacity. Append one same-hash
  pool row, as native duplicate-row precedent permits; original row stays exact.
- State gate excludes undiscovered Twin. Append visual-only Twin hook to frozen
  mapmenu; wrap create/cleanup, keep original code bytes. No progression writes.
- Build four-file probe with strict source pins, inverse checks, active record
  checks, exact relocation sets, fresh Lua 5.1 tests, and tamper rejection.
- Reuse pinned transaction engine through `-LibraryOnly`; no retired install.
- Run old offline suites, new suites, fake-root rollback/failure tests, independent
  review, then fresh verification and commit. Stop before real install.

Main risks: pool leak on reopen, failed cleanup, changed Raven/native bytes,
wrong coordinate join, runtime wrapper widening file set, hidden source drift.
Tests must cover each. Lua mocks prove hook control flow, not engine pixels.
