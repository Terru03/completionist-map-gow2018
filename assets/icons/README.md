# Icon assets

This folder contains original Completionist Map UI artwork. It should be compatible with the visual language of God of War (2018) without reproducing official icon art 1:1.

## Source policy

- `source/` contains canonical 64-unit SVG glyph masters.
- Source glyphs use a transparent background.
- Surface shells and state treatments should be layered separately where technically possible.
- Raster targets are 24, 32, 48 and 64 px.
- 24/32 px exports require visual inspection for optical simplification.

## Source colours

- Bone: `#E8E3D6`
- Charcoal outline: `#252B2C`

Runtime tinting may replace the bone colour for hover, selected, tracked, completed or unavailable states.

## Initial acceptance set

The first four source glyphs are Raven, Nornir Chest, Nornir Seal and Nornir Bell. They are intentionally more geometric than illustrative so they survive compass-size rendering.

See `docs/ICON-DESIGN-SYSTEM.md` for the full inventory, state matrix, naming rules and visual rationale.
