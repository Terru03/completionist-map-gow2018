# All Collectibles Production Plan

## Locked production base

The Raven implementation is now the accepted production baseline.

- accepted Raven commit: `f665f61935e1723c2b68d1e162cbde228e7de89b`
- `main` fast-forwarded to that commit
- permanent recovery branch: `release/ravens-v0.10.5-proven`
- active integration branch: `codex/all-collectibles-production`
- research archive only: `codex/all-collectibles-production-research`

Do not merge the research branch wholesale. It diverged before the final Raven
authority, compass, filter, and Mystic Gateway fixes. Port only specific research
artifacts or code after reviewing them against this production base.

## Raven lock

Raven behavior is an invariant for all future collectible work.

The following Raven-specific assets are frozen unless a separate Raven regression
task explicitly authorizes a change:

- `catalogue/odins-ravens.json`
- `catalogue/odins-ravens-save-identities.json`
- `tools/v0.10.5/all-ravens-map-runtime.lua`
- `tools/v0.10.5/all-ravens-gameplay-events.lua`
- the accepted Raven filter / fast-travel visibility contract
- the accepted Raven native snapshot protocol and save-boundary semantics

Shared infrastructure may grow around Ravens, but every change must preserve:

1. exact alive/killed set on advanced saves;
2. all 53 on a true fresh save;
3. immediate kill removal;
4. persistence after reload;
5. cross-save revival/isolation;
6. custom Raven map artwork and compass ownership;
7. Show All / Completionist / RAVENS filter behavior;
8. hidden Ravens on unrelated filters;
9. no Ravens on Mystic Gateway fast-travel maps;
10. no save, progression, process-memory, or static-descriptor writes.

The Raven offline and live proof suites remain mandatory regression gates.

## Architecture

Do not duplicate the full Raven implementation separately for every family.
Reuse the proven Raven contract while keeping Raven-specific code frozen.

Each collectible family gets:

1. exact static catalogue;
2. exact stable physical identity;
3. exact map coordinates / realm / region;
4. read-only loaded state adapter;
5. read-only persisted/unloaded state resolver;
6. fail-closed `unknown` state;
7. family-specific map artwork;
8. stock-compatible filter participation;
9. automatic suppression on Mystic Gateway fast-travel maps;
10. exact selection / compass add-remove-replace behavior;
11. immediate disappearance when completed;
12. save-load and cross-save authority;
13. deterministic offline build + rollback proof;
14. targeted live proof before integration.

The family-neutral resolver must return only:

- `remaining`
- `complete`
- `unknown`

Unknown never creates a marker.

## Research branch facts to preserve

The old research branch already established useful static evidence:

- Lore Markers: 43 physical / 43 tracked.
- Legendary Chests: 64 physical raw rows; 33 tracked production rows;
  27 exact trial-reward exclusions; 4 unresolved nontracked rows.
- Artefacts: 45 physical rows; Ship Heads currently prove 9 physical placements
  while native target bookkeeping says 10.
- Nornir Chests: 22 physical rows; exact per-object RegionSummary binding remains
  unresolved for the tracked candidates.
- Nornir Seals: 30 child objects.
- Nornir Bells: 24 child objects.
- Nornir Mechanisms: 12 child objects.
- Niflheim procedural chest templates are not fixed world markers and remain
  excluded until runtime spawn identity is proved.

The old research also correctly identified the main blocker:
exact unloaded / persisted per-object state for non-Raven collectibles.

## Implementation order

### Phase 0 — transplant evidence, not runtime history

Selectively port from `codex/all-collectibles-production-research`:

- final static catalogue/schema tooling;
- production-status documentation;
- family-neutral runtime model/tests;
- exact source/audit evidence needed by the chosen family.

Do not import old experimental Raven runtime or old generated candidate bytes.

### Phase 1 — family-neutral persisted-state resolver

Generalize the proven Raven read-only native authority path without changing the
existing Raven wire contract.

Requirements:

- exact catalogue identity to persisted object state;
- loaded and unloaded objects;
- no nearest-coordinate, ordering, filename-only, or aggregate-only inference;
- aggregate RegionSummary may validate state but cannot substitute for exact
  per-object authority;
- malformed/missing/ambiguous results become `unknown`;
- Raven protocol remains byte/behavior compatible.

### Phase 2 — Legendary Chest vertical slice

Use tracked Legendary Chests as the first new production family.

Why first:

- 33 exact tracked production rows already exist;
- completion semantics are a direct opened/not-opened state;
- 27 trial rewards are already positively classified and can remain excluded;
- 4 unresolved nontracked rows can remain fail-closed without blocking the 33
  exact tracked rows.

Acceptance requires at least one mixed save with known opened and unopened
Legendary Chests, including unloaded examples.

### Phase 3 — Lore Markers

Static coverage is already 43/43. Prove exact read/discovered persistence field,
then apply the same production contract.

### Phase 4 — Artefacts

Implement only exact production rows. Resolve the Ship Head 9-versus-10 native
bookkeeping discrepancy before claiming complete Ship Head coverage. Never invent
a tenth physical marker.

### Phase 5 — Nornir system

Handle Nornir last among fixed collectibles because it is relational:

- chest parent;
- seal / bell / mechanism children;
- exact parent binding;
- parent completion suppresses children;
- child state never independently completes the parent.

Do not restore the old inferred 20-row joins without new exact evidence.

### Phase 6 — procedural / special cases

Niflheim procedural rewards and any unresolved/story/trial rows stay excluded
until stable runtime spawn identity and completion semantics are proved.

## Branch policy

`main`
: latest field-proven stable product only.

`release/ravens-v0.10.5-proven`
: permanent Raven recovery point; do not advance it.

`codex/all-ravens-release-candidate`
: historical Raven RC; no new collectible development.

`codex/all-collectibles-production`
: integration branch containing only families that passed their gates.

Per-family work should occur on short-lived branches from
`codex/all-collectibles-production`, for example:

- `codex/collectible-legendary-chests`
- `codex/collectible-lore-markers`
- `codex/collectible-artefacts`
- `codex/collectible-nornir`

A family merges into the production branch only after its targeted live proof and
the full Raven regression gate both pass.

## Immediate next task

Start Phase 0/1 by selectively recovering the final generic collectible
catalogue/state research from `codex/all-collectibles-production-research`,
then use the proven Raven native authority architecture to build a
family-neutral read-only persisted-state resolver.

The first production vertical slice should be tracked Legendary Chests.
