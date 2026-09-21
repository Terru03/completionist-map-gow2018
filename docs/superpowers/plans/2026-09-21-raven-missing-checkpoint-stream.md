# Missing Raven checkpoint stream plan

Task: `docs/research/ASTRA-v0105-raven-missing-checkpoint-stream-task.md`.
Start commit: `76c46b5`. Keep current Raven worktree and branch. Leave prior dirty files alone.

- [x] Pull branch; read new task, handoff, dual-channel capture, and prior restore proof.
- [ ] Trace full staged WAD record and Channel A consumer. Track pointers and lengths through concrete calls. Check split unwind fragments.
- [ ] Trace buffers at `0x465143` and `0x4651E2` back to producer. Distinguish live serialization from checkpoint restore.
- [ ] Archive bounded instruction evidence and field/ownership findings. Commit/push stage; handoff must name evidence commit and unresolved gap.
- [ ] If proof yields retained structure, build bounded RPM observer with existing codecs, SHA pin, snapshot checks, exact matching, and one archive/push runner. No game launch or state writes.
- [ ] Independent review, fresh Python/tests/PowerShell checks as relevant, requirement audit, final commit/push. If user capture needed, give one exact command and stop.

Acceptance: exact Raven states only; absence stays unknown. Veithurgard `false,true,true` and second region needed before authority claim. No map integration before stream and unloaded coverage proven.

Checks: EXE SHA `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`; SQLite `mode=ro`; report RVAs and instruction bytes. Review security of any process reader or runner. No broad memory scans, force push, merge, save writes, or unrelated staging.
