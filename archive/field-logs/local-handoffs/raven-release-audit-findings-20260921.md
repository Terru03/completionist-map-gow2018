# Raven release audit findings

Audit baseline: `5f0f593`. Work branch: `codex/raven-release-adversarial-audit`.

## A01 — release-blocking: compass intent and UI settlement races

Paths: `tools/v0.10.5/all-ravens-map-runtime.lua` (`ShowOnCompass`, `Update`, `refreshPrompt`, `hideExactTracked`, `beginAuthorityBoundary`).

Repro: Add A; delay native Hide A; Remove A; Add A before hide settles. Old code reads stale custom IDs and treats third click as remove. Separate repro: let add/remove settle, then let base update overwrite footer. Old code has dropped prompt intent and leaves stale text. Hover B while A settles: A's Remove text overwrites B's Replace text. Kill tracked A then inject legitimate stock: stale owner erases stock. Arm A selection then load boundary: stale selection swallows next stock action.

Fix: latest explicit action decides toggle. Tracked intent restores target after delayed native hide. Keep settled UI intent while cursor owns same Raven; use actual hovered Raven when cursor moves. Settled remove releases stock ownership. Kill and boundary clear stale ownership/selection.

Evidence: `runtime-captures/raven-release-adversarial-audit-20260921/lua-compass-red.txt` records five deterministic failures; `lua-remove-prompt-red.txt` records late remove overwrite. `lua-compass-green.txt`: 24 Lua 5.1 tests pass. Existing realm, state, alias and stock paths remain covered. Live retest still needed for changed runtime.
