# Icon assets

This folder contains original Completionist Map UI artwork. It should fit the visual language of God of War (2018) without reproducing official icon art 1:1.

## Layout

- `source/` contains canonical 64-unit SVG glyph masters used for production work.
- `concepts/` contains approved high-resolution PNG concept masters and any retained alternate SVG studies.
- `incoming/` is only a temporary upload handoff and should normally remain absent/empty.

## Source policy

- Source glyphs use a transparent background.
- Surface shells and state treatments should be layered separately where technically possible.
- Production raster targets are 24, 32, 48 and 64 px.
- 24/32 px exports require visual inspection and optical simplification.
- PNG concept masters are visual references for the final SVG/production assets, not direct in-game exports.

## Source colours

- Bone: `#E8E3D6`
- Charcoal outline: `#252B2C`

Runtime tinting may replace the bone colour for hover, selected, tracked, completed or unavailable states.

## Approved concept families

- Raven
- Nornir Chest
- Nornir Seal
- Nornir Bell
- Nornir Mechanism
- Lore Marker
- Artefact
- Legendary Chest
- Remaining Collectible
- Player Marker

The spread-wing Raven direction (concept C) is the canonical Raven source.

See `docs/ICON-DESIGN-SYSTEM.md` for the full inventory, state matrix, naming rules and visual rationale.
