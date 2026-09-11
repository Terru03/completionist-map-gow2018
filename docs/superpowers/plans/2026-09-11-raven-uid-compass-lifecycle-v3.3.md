# Raven UID Compass Lifecycle v3.3 Plan

## Goal

Fix only Twin prompt/action ownership exposed by human v3.2 runtime proof. Preserve
real Raven routing, lifecycle cleanup, Twin lifetime, stock isolation, five-file
package, and transaction safety.

## Observed failure

Exact Twin collision captures the Twin object and UID. Older stock code also puts
that same Twin UID in `currMarkerID`. v3.2 treats every non-nil `currMarkerID` as a
stock owner, disarms the exact Twin candidate, and delegates the action to Dock.

## Contract

- Capture custom identity only from exact real/Twin collision object references.
- Real prompt ownership stays unchanged: real custom bridge selected, Nornir state
  absent, and `currMarkerID` nil.
- Twin prompt ownership requires visible prompt, exact Twin collision provenance,
  non-nil `currMarkerID`, and string-equal candidate/current IDs.
- Stock ownership requires non-nil `currMarkerID` different from the exact current
  custom candidate ID. Repeat this test at action time.
- Never infer Twin ownership from `currMarkerID` alone.
- Keep no-TTL one-shot state machine and every v3.2 disarm/cleanup path.
- Keep gameplay lifecycle event source byte-identical and package binaries unchanged.

## Verification

1. Reproduce archived same-ID Twin disarm against v3.2.
2. Make v3.3 tests fail with captured Twin runtime shape before router change.
3. Prove Twin full candidate/arm/consume/show chain and `CompletionistRaven` call.
4. Prove different stock ID delegates, marker ID alone cannot hijack, real path is
   unchanged, replacement stays single-target, second click removes, and Twin still
   routes after real completion.
5. Run package, gameplay lifecycle, Twin lifetime, routing, deterministic rebuild,
   LF/CRLF, transaction, focused Raven, and broad v0.10.4 suites.
6. Commit, pin source blobs, run canonical verifier, then push v3.3 branch only.
