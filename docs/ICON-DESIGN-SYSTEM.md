# Completionist Map Icon Design System

Status: initial production specification

This document defines the original icon family used by Completionist Map. The visual language should feel compatible with God of War (2018) without tracing or reproducing official icon artwork.

## Design goals

- Norse, restrained, carved and slightly runic.
- Strong silhouette recognition at 24 px.
- Category is communicated primarily by shape, not colour.
- State is communicated primarily by tint, shell, halo and opacity.
- One source glyph should serve map, compass and filter surfaces wherever possible.
- Nornir chest parent markers must remain visibly different from Nornir puzzle-child markers.

## Base grid

- Master SVG viewBox: `0 0 64 64`.
- Primary source files are glyph-only and transparent.
- Map/filter/compass shells are composed separately.
- Target raster sizes: 24, 32, 48 and 64 px.
- 24 and 32 px exports should be visually checked and, if necessary, optically simplified instead of blindly downscaled.

## Palette

| Role | Value |
| --- | --- |
| Default glyph | `#E8E3D6` |
| Dark outline | `#252B2C` |
| Secondary cold grey | `#899597` |
| Hover | `#B7DBE5` |
| Selected | `#F0D58A` |
| Tracked | `#D8A849` |
| Completed | `#777F7D` |
| Unavailable | `#686D70` |
| Priority red, exceptional use only | `#A84D43` |

Hidden/filter-disabled should normally use 25-35% opacity rather than a new category colour.

## Shape language

- Angular geometry with small asymmetries.
- Strong triangular, diamond, shield and chipped-stone forms.
- Very limited interior engraving.
- Maximum two important interior details at 24 px.
- No thin knotwork, ornate Celtic filigree, realistic illustrations or generic fantasy-RPG scroll/vase symbols.
- Perfect circles are mainly reserved for state rings or interaction shells.

## Inventory

| Family | Meaning | Map | Compass | Filter | Strategy |
| --- | --- | :---: | :---: | :---: | --- |
| Raven | Odin's Raven | yes | yes | yes | Original angular raven glyph |
| Nornir Chest | Parent Nornir objective | yes | yes | yes | Broad, horned stone-chest silhouette |
| Nornir Seal | Breakable child object | yes | yes | optional | Fractured rune tablet |
| Nornir Bell | Timed child object | yes | yes | optional | Hanging angular bell |
| Nornir Mechanism | Spinner/totem/switch child | yes | yes | optional | Tall rune pillar with rotation cue |
| Nornir Generic | Unknown Nornir child | yes | yes | optional | Compact rune diamond / fragments |
| Lore Marker | Lore/readable object | yes | yes | yes | Tall standing-stone silhouette |
| Artefact | Portable collectible relic | yes | yes | yes | Chipped amulet/relic silhouette |
| Legendary Chest | Legendary chest | yes | yes | yes | Narrow reinforced chest with radiant split |
| Generic Remaining | Unknown remaining collectible | yes | yes | yes | Three rune fragments around centre |
| Player | Current player | native preferred | no | yes | Reuse native map player marker if technically available; custom filter glyph only when needed |

## Nornir hierarchy

The Nornir Chest is the parent objective and should be visually heavier than its children.

Parent:
- Wide horizontal silhouette.
- Full map-marker shell.
- Higher visual mass.

Children:
- Smaller glyph footprint.
- No long map-pin tail unless the implementation requires one.
- Vertical or compact silhouettes.
- Interaction-specific shape: crack, bell, rotation.

Do not represent a Nornir Seal as a bare rune. A bare rune is too easy to confuse with Lore. The crack is the defining feature.

## Category concepts

### Raven
Angular raven in three-quarter/profile hybrid, with a hooked beak and strongly simplified wings. Avoid realistic feather detail.

### Nornir Chest
Broad stone chest with heavy lid, slight horn-like upper corners and a central rune notch. It should be the widest collectible glyph in the family.

### Nornir Seal
Compact chipped tablet with one rune-like incision and an unmistakable diagonal fracture.

### Nornir Bell
Angular hanging bell with visible clapper. The hanging silhouette must survive at 24 px.

### Nornir Mechanism
Tall carved pillar or totem with one simple rotation cue. The interaction, not detailed prop accuracy, is the important message.

### Lore Marker
Tall carved standing stone. Avoid a book or scroll because those read as generic RPG rather than the game's world language.

### Artefact
Small portable relic or amulet with an intentionally chipped corner. Avoid representing a single artefact set such as a vase because artefacts vary.

### Legendary Chest
More compact and vertically reinforced than the Nornir Chest, with a sharp central split or radiant notch. At 24 px the two chest families must still differ by outer silhouette.

### Generic Remaining
Three angular rune fragments around a centre point. Avoid a modern question mark.

## States

The category drawing remains stable between states.

| State | Treatment |
| --- | --- |
| Default | Bone-white glyph, restrained dark outline |
| Hovered | Frost-blue rim/halo, optional 105% scale |
| Selected | Pale-gold shell or outer diamond |
| Tracked | Amber-gold shell/halo, compass visibility enabled |
| Completed | Muted stone grey, lower opacity |
| Unavailable | Dark desaturated grey |
| Hidden | 25-35% opacity in filter UI; no marker on map |
| Undiscovered | Generic fragment glyph if spoiler-safe mode needs it |

Completed, unavailable and hidden should normally be renderer treatments rather than separately redrawn SVGs.

## Surfaces

### Map
- Full category glyph.
- Optional common shield/lozenge marker shell.
- Dark outer separation for bright terrain areas.
- Selected/tracked state can add a reusable outer ring.

### Compass
- Glyph-only or glyph plus very small diamond base.
- Remove secondary engraving.
- Prefer 24 or 32 px masters optimised for silhouette.

### Filter/menu
- Same category glyph whenever possible.
- 32 or 48 px.
- Enabled/disabled represented by opacity/state treatment, not alternative category artwork.

## File naming

Pattern:

`<family>_<surface>_<state>_<size>.png`

Examples:

- `raven_map_default_32.png`
- `raven_compass_tracked_24.png`
- `nornir_seal_map_selected_32.png`
- `legendary_chest_filter_default_48.png`

SVG source names omit surface/state where the glyph is shared:

- `raven.svg`
- `nornir_chest.svg`
- `nornir_seal.svg`
- `nornir_bell.svg`

## Proposed asset layout

```text
assets/icons/
  source/          # canonical SVG glyphs
  map/24/
  map/32/
  map/48/
  map/64/
  compass/24/
  compass/32/
  filter/32/
  filter/48/
  states/          # reusable shells/halos/overlays if raster assets are required
```

## Minimum viable production pack

First production pass:

1. Raven
2. Nornir Chest
3. Nornir Seal
4. Nornir Bell
5. Nornir Mechanism
6. Lore Marker
7. Artefact
8. Legendary Chest

First state/surface matrix:

- Main collectible families: `map_default`, `map_selected`, `compass_tracked`, `filter_default`.
- Nornir child families: `map_default`, `compass_tracked`.
- Keep the native Kratos/player marker where possible.

The first visual acceptance gate is Raven + Nornir Chest + Nornir Seal + Nornir Bell at 24 px. If those remain immediately distinguishable in-game, the family is structurally sound.
