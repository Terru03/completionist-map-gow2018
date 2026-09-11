# Raven UID compass lifecycle v3.2

## Goal

Replace v3.1's 30-frame pending-selection TTL with a map-UI-lifecycle state
machine. Keep exact Raven/Twin object-reference identity, stock delegation,
single-active replacement, and the runtime-proven gameplay cleanup unchanged.

## Production signals

- `MapOn:MapCollisionChangeHandler` sees the exact Raven or Twin game object
  before the base handler clears transient collision state.
- The base custom-Raven path sets `completionistMapV100Selected=true`, clears
  `currMarkerID`, and calls `GetShowOnCompassPrompt` from its reticle update.
- A native stock prompt is confirmed when `GetShowOnCompassPrompt` is visible
  with `currMarkerID` set and the custom-Raven owner false.
- Nornir prompts are confirmed different owners because their selection fields
  are set while `completionistMapV100Selected` is false.
- Empty/noncustom collision callbacks during the six-frame base debounce retain
  the custom-Raven owner. They are noise, not proof of a new selection.

## State machine

- `none`: no custom action may be consumed.
- `candidate-custom`: exact collision captured name, UID, kind, and generation.
- `armed-custom`: base prompt is visible and owned by the custom-Raven path.

Transitions:

1. Exact Raven/Twin collision creates or replaces candidate.
2. Visible custom-Raven prompt arms candidate.
3. `ShowOnCompass` consumes armed identity once and returns to none.
4. Visible prompt owned by stock or another custom feature disarms.
5. Unavailable prompt, map teardown, or real Raven completion disarms.
6. Incidental noncustom collision alone makes no state change.

`ShowOnCompass` also checks `currMarkerID` before consume. This is a final
fail-safe if native action dispatch happens without another prompt callback.

## Test matrix

Use Lua 5.1 production-shaped tests for 300+ frame delay, noncustom noise,
custom replacement, stock/Nornir disarm, one-shot consume, teardown, completion,
Twin after completion, all one-active transitions, and hide-failure fail-closed
paths. Then run lifecycle, Twin, package, Raven, broad v0.10.4, deterministic
rebuild, LF/CRLF, and transaction self-tests.
