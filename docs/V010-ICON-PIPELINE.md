# v0.10.0 custom icon pipeline

`Completionist-Map-v0.10.0-ICON-PIPELINE.zip` is built from the stable v0.9.6.1 behavioural base.

## Goal

Establish the production path for the user-authored Completionist artwork without regressing Raven/Nornir map, filters, deep zoom, hidden-Kratos centring or direct-XYZ HUD compass behaviour.

## Asset staging

The installer uses the user's authenticated GitHub CLI session to fetch every PNG master from `feat/completionist-icon-system/assets/icons/concepts/`:

- `raven_concept_master.png`
- `nornir_chest_concept_master.png`
- `nornir_seal_concept_master.png`
- `nornir_bell_concept_master.png`
- `nornir_mechanism_concept_master.png`
- `lore_marker_concept_master.png`
- `artefact_concept_master.png`
- `legendary_chest_concept_master.png`
- `remaining_collectible_concept_master.png`
- `player_marker_concept_master.png`

They are stored under `mods/completionist-map/icons/concepts` and resized, preserving alpha/aspect ratio, to 24/32/48/64 px candidates under `mods/completionist-map/icons/generated/<size>`.

`manifest.json` records source dimensions, SHA256 and production paths.

## Runtime rendering discovery

The exposed GoW Lua sources show authored `SetMaterialSwap` use, but no proven loose-PNG texture-binding API. v0.10.0 therefore probes only the safe synthetic map duplicates for plausible direct setters (`SetTexture`, `SetTextureName`, `SetImage`, `SetImagePath`, plus UI equivalents).

If such an API is actually exposed, the build attempts the staged 32 px file under `pcall` on the synthetic Raven/Nornir duplicate. If no direct setter exists, the existing DockPoint proxy remains visible and the log records the capability result rather than guessing or altering game assets.

The borrowed HUD proof carrier is capability-probed only. Unknown setters are not invoked on it.

## Diagnostics

New prefixes:

- `ICON_CAPS`
- `ICON_BIND_ATTEMPT`
- `ICON_BIND_RESULT`
- `HUD_ICON_CAPS`

These determine whether the next production step can use loose PNGs directly or must proceed through authored material/texture-pack replacement.

## Safety

The build retains the ordinary test invariants:

- no `Map.ChangeMarkerState()`;
- no synthetic `game.Compass.ShowMarker()`;
- no artificial summary/progression mutation;
- no synthetic save writes.
