# Registry research plan

Scope: work through `astra-v104-map-class-registry.md` on `feat/v0.10.4-all-ravens`.
Game and saves stay read-only. No launch, install, payload commit, or Raven rollout.

1. Pull branch; run required pool inventory. Fix failure before donor search.
2. Join all pool hashes to WAD names, payload names, IDs, prototypes, and scopes.
3. Trace native Icon lookup, pool setup, duplicate handling, and pool checkout.
4. Check pinned GoWLUA and mapmaster use. Keep unknown use unsafe.
5. Compare four custom-class routes. Build proof only if every donor gate passes.
6. Save tools, JSON evidence, concise findings, and explicit unknowns.
7. Test malformed input, report path guards, duplicate handling, and source pins.
8. Get independent code review; rerun checks; commit and push tools and findings.

First run hit Python alias bug in PowerShell. Fixed command invocation; inventory
then found 13 pooled map classes, no zero-use donor, one duplicate group. Full
pool/resource trace follows; no safe runtime test assumed.
