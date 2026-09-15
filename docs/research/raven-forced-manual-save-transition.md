# Exact Raven forced-manual save transition

## Result

Status: **PASS_EXACT_CAUSAL_SAVE_TRANSITION** for the tested Raven kill.

Production unloaded-state oracle: **STILL BLOCKED / FAIL CLOSED**.

Runtime generation: **NOT ALLOWED YET**.

## Target

- Catalogue ID: `raven_95b9c6444d479ac68207b1829d02909b`
- Physical GUID: `95b9c644-4d47-9ac6-8207-b1829d02909b`
- Object: `goprecisionchallenge_raven_perch`
- Progression field: `ravenKilled`
- Parent quest: `RegionSummary_ALF_Raven_Parent`
- Adapter: `precisionchallenge_checkpoint_ravenKilled`

## Controlled manual-save experiment

The player supplied the manual-save ordering from the in-game save UI:

- pre-kill manual save: `2026-09-15 22:54:41 +03:00`
- post-kill manual save: `2026-09-15 22:55:12 +03:00`

Only the target Raven was killed between those saves.

The ring-buffer mapping for that chronological pair is:

- pre-kill: physical slot 17
- post-kill: physical slot 18

Both logical saves contain 81 validated zlib streams.

Sequence alignment produces exactly one changed run: stream 27 is replaced by stream 27.

Pre-kill stream 27:

- compressed bytes: 73
- decompressed bytes: 79
- SHA-256: `a20550b246cb5e25acc12402c64093110969eff4ba1fdd2b66e6850d359d2172`
- known fields: `mapSummaryComplete`

Post-kill stream 27:

- compressed bytes: 96
- decompressed bytes: 116
- SHA-256: `620bb85be8fd0ebf9c778eb06aba0e532ca57c74bec2d2252694512728e7f308`
- known fields: `ravenKilled`, `mapSummaryComplete`

No other zlib stream changes in the chronological pair.

## Interpretation

This is exact causal evidence that killing the tested Raven changes one serialized save stream and introduces the `ravenKilled` field into that stream.

It corrects the earlier nearest-content match (`alive slot 5 -> dead slot 18`), which was semantically identical and therefore not the chronological manual-save pair. The save-menu timestamps establish `17 -> 18` as the correct controlled transition.

This does **not** yet prove a production unloaded-state oracle for arbitrary saves. The remaining missing edge is a stable way to identify the owner of this stream independently of ring-slot ordinal/runtime allocation history. A stream ordinal or whole-stream hash must not be treated as a permanent collectible key.

Next research target:

`exact target static identity -> stable serialized stream owner/key -> ravenKilled presence/value`

Until that edge is proved, unknown state remains hidden and runtime catalogue generation stays disabled.

## Evidence

Primary archive commit: `06c86d7bd7ce14c431eb493c98e6902e49b42042`

Archive path:

`archive/field-logs/save-captures/gow-raven-forced-manual-chronological-20260915-225839/`
