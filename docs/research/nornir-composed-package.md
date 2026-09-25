# Raven + Nornir package verification, 2026-09-25

The current frozen package contains 53 Raven markers and 301 `WAD_R_UI`
GOPool rows. The active stock-art Nornir checkpoint adds 88 distinct markers
and pool rows, for 389 total. The v0.10.4 map/HUD builder's 257-to-259 plan
belongs to the earlier one-Raven experiment. Its PowerShell runner now checks
the current branch and stops before building when given the current package.
The historical Raven-only production verifier remains unchanged.

The read-only composed verifier is
`tools/v0.10.5/verify-nornir-composed-package.py`. It pins the frozen
all-Ravens package, then checks every baseline WAD physical record (apart from
the two accounting payloads), all 301 original UI pool rows, Raven compass
class and in-world carrier bytes, all original map and coordinate rows, Raven
texture pack, compass graph, boot options, and distinct Nornir marker IDs. It
checks added Nornir resource IDs and the Nornir class-to-HUD-to-carrier bindings.
Sparse offline candidate roots can be layered over a base game root.

Read-only verification of the installed V4 stock-art checkpoint passed. The
historical four-family art package also passed structural verification: 88
Nornir markers, 397 UI pool rows, and four dedicated Nornir compass classes
with four dedicated in-world carriers. Its WAD SHA is already known to fail the
live Raven art check. The chest-only art package likewise passed all
structural checks, yet its live Raven art check failed. Thus exact inverse
construction protects file content but cannot establish renderer isolation.
The verifier marks known failed WADs and never reports installation eligibility
or live art proof.

```powershell
py -3.14 -B tools/v0.10.5/verify-nornir-composed-package.py --report build/nornir-composed-verifier/current-v4.json
py -3.14 -B tools/v0.10.5/test_verify_nornir_composed_package.py -v
```

The first pack-registration-only diagnostic was rolled back without live
testing. After the 22:37-22:38 screenshots confirmed the V4 fallback and the
game closed, a new pack-only operation was installed and structurally verified
at `build/nornir-pack-only-probe/backups/3102efb8ff59477cbc7683f3480dc692/operation.json`.
Its live result is the next discriminating evidence: if Raven art changes with
the extra texture pack and no new WAD, pack registration is sufficient; if it
stays correct, WAD references or lazy texture loading still need investigation.
No custom-art candidate should be installed based solely on this structural
report.
