# Completionist Map for God of War (2018)

A PC mod for **God of War (2018)** that adds custom collectible markers to the game's world map and compass, with completion-aware behaviour designed for a full completionist playthrough.

Production build contains **551 marker records across 16 custom collectible families**. The current package is **v1.0.4**, including the player-tested chest-tracking fix and Windows 10 startup fix. [Nexus Mods](https://www.nexusmods.com/godofwar/mods/396?tab=files) remains the release page; scan and manual-review status are recorded in the [v1.0.4 release record](docs/releases/v1.0.4-release.md).

## What it does

Completionist Map extends the native map and compass with custom markers for **16 collectible families**:

- Odin's Ravens
- Nornir Chests
- Nornir Seals
- Nornir Bells
- Nornir Mechanisms
- Legendary Chests
- Cipher Chests
- Wooden Chests
- Red / Coffin Chests
- Artefacts
- Jötnar Shrines
- Lore Markers
- Lore Scrolls
- Realm Tears
- Treasure Maps
- Treasure Dig Sites

All 16 families are part of Completionist Map. Some families use different internal completion-state sources where required by the game. For example, Odin's Ravens use their proven native authority path internally, but they are part of the same mod and the same completionist marker experience.

The mod follows a strict **no-duplicate-native-marker** policy. It does not add redundant Completionist Map pins for content that already has adequate native map and compass support, including **Valkyries, the Valkyrie Queen, Mystic Gateways and Shops**. Artwork for some native-only categories may exist in the repository's design/research asset pool, but those assets are not active custom marker families.

Markers added by Completionist Map use original, category-specific artwork designed to fit the God of War UI rather than reusing unrelated stock icons.

## Features

- 551 marker records across 16 custom collectible families
- Custom world-map markers across the production collectible catalogue
- Custom compass HUD icons with native-feeling direction and distance tracking
- Add, replace and remove compass-target behaviour
- Completion-aware marker handling so completed content can be hidden correctly
- Native/read-only authority paths for progression-sensitive collectible state
- Map filtering and marker visibility integration
- In-map marker show/hide control
- State handling across map reopen, reload and realm transitions
- Original marker artwork and texture-pack pipeline
- Automated installer and uninstaller with stock-file backup support

The mod does **not** manufacture quest progress or mark collectibles complete for the player.

## Release status

v1.0.4 fixes opened chest markers when the live scene collapses outer catalogue ancestors, and fixes the early Windows compatibility call involved in a reproduced startup crash. It includes the earlier Realm Tear, Artefact and live compass-clearing fixes.

The startup reporter confirmed successful launch on 2026-10-06. On 2026-10-08 the author relayed successful Discord feedback for the chest-test package; the tester confirmed opened red/common chest pins disappear and killed Ravens are tracked correctly. This release preserves all tested runtime and installer bytes. See the [release record](docs/releases/v1.0.4-release.md), [chest regression](docs/builds/2026-10-06-chest-state-feedback.md), and [native startup analysis](docs/builds/2026-10-06-windows10-startup.md) for evidence and remaining test limits.

Older issues, research notes and archived probes remain in the repository as development history. They should not be interpreted as current release blockers.

## Installation

The Nexus package is built around the included one-click installer:

1. Extract the release archive.
2. Close God of War.
3. Run `Install.bat`.
4. The installer locates the game, backs up affected stock files and installs the mod.
5. Launch God of War and open the map.

`Uninstall.bat` restores the backed-up stock files and removes the mod-added files.

Manual and mod-manager installs must register `../../patch/pc_le/completionist_v105_family_art` in existing `patch-texpacks` array in `exec/boot-options.json`, keeping all other entries. These paths bypass installer hash checks; follow package README and supported EXE hash below.

## Compatibility

Supported EXE only: Steam **1.0.13**, file version **1.0.475.7534**, SHA256 `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`.

No Epic or modified-EXE support claim. Installer discovers several game paths but rejects unsupported EXE before changes. Other mods must not replace `dxgi.dll` or same patched resources.

## Requirements

- God of War (2018) for PC
- GoW Script Loader & Gameplay Tweaks 0.22 (`version.dll`), installed first
- Windows 10 or Windows 11 x64. The affected Windows 10 startup reporter confirmed launch with the v1.0.4 native fix.

## Using the mod

Open the world map normally. Completionist markers participate in the map UI alongside the game's own markers.

A collectible marker can be selected and tracked on the compass. The mod keeps the stock single-target behaviour: adding another destination replaces the active target, and the selected destination can be removed again from the map.

Completed collectibles are handled by the appropriate production completion source rather than by synthetic save/progression writes.

## Repository layout

This repository contains the mod's source patches, native bridge code, Lua runtime code, collectible catalogues, build and packaging tools, original marker artwork, tests, and the research trail used to reach the production implementation.

Important areas include:

- `native/` - native completion-state and runtime bridge code
- `tools/` - runtime, validation, packaging and installer tooling
- `catalogue/` - collectible catalogues and identity data
- `config/` - production collectible configuration
- `assets/` - original marker artwork and design sources
- `docs/` - implementation and research documentation
- `archive/` - historical field logs, probes and evidence

The large research archive is intentionally retained as provenance for the reverse-engineering and validation work behind the mod.

## Development history

The project began with a single Odin's Raven proof of concept, then expanded through full Raven tracking, Nornir support, individual collectible-family research and finally the unified production Completionist Map.

The current `main` branch represents the integrated production implementation. Historical prototype documents and closed issues may describe approaches that were later replaced.

## Safety philosophy

The mod was developed around a few strict rules:

- do not fabricate collectible completion
- do not write fake quest or region-summary progress
- prefer read-only observation of native game state
- fail closed when a progression state cannot be trusted
- preserve stock files through reversible installation and backup paths

## Nexus Mods

[Completionist Map on Nexus Mods](https://www.nexusmods.com/godofwar/mods/396). See the [v1.0.4 release record](docs/releases/v1.0.4-release.md) for the current file, scan result and manual-review request. A successful player test does not establish Nexus malware verification or download availability.

## License

No separate open-source or artwork reuse licence has been granted yet. Please ask before redistributing or reusing source code or original marker artwork.
