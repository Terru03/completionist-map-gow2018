# Stock-icon Nornir family test, 2026-09-25

Three successive custom-art WAD builds made Raven pins and Nornir child pins
draw chest art in live screenshots. The latest evidence is
`Screenshot 2026-09-25 143248.png` (selected Nornir Seal) and
`Screenshot 2026-09-25 143255.png` (selected Odin's Raven), both under
`C:/Users/david/Pictures/Screenshots`. The prior 17-file candidate was rolled
back with all seven Raven-base hashes restored and ten new files removed. The
three failed custom WAD hashes are blocked by the native installer.

This test uses four existing map resources. It retains the 22 separate Nornir
chest IDs, 66 separate child IDs, exact locked-attempt child reveal, seal break
and reward-open events, map filters, and compass ownership handoff. The first
stock test used `DockPoint` for every family. The 14:47:31 and 14:48:09
screenshots show its dock flag on the compass for a chest and seal. The 14:47:55
map screenshot shows separate Nornir pins and restored Raven art. That first
operation was rolled back, and its replacement uses these stock compass classes:

| Family | Existing map resource | Existing compass class | HUD resource |
| --- | --- | --- | --- |
| Chest | `goMapIconSecondaryQuest` | `SIDE` | `gosidequest` |
| Seal | `goMapIconValkyrie_location` | `Valkyrie` | `govalkyrie` |
| Bell | `goMapIconFight_location` | `FightLocation` | `gofightlocation` |
| Rune mechanism | `goMapIconAreaEntrance` | `AreaEntrance` | `goentrance` |

The six changed files are `mapmaster.dcb`, `mapcoords.dcb`, `wad_r_ui.dcb`,
`mapmenu.lua`, and the two stock chest-script overrides. The WAD artwork,
compass-class DCB, compass graph, and boot options are not changed. The four
compass classes were read back from the installed Raven `wad_r_perm.dcb`; all
four are non-main-quest classes and resolve to distinct stock HUD resources.
The added
pool capacity consists of 88 one-slot rows, one per Nornir marker, divided
among the four stock resources. The 301 existing pool rows are unchanged and
the pool edit has an exact inverse.

Offline tests pass for deterministic build output, existing Raven rows,
distinct family resources, Lua 5.1 compilation, locked-attempt child reveal,
compass handoff, rollback, partial-install rollback, and drift refusal. The
installer verified all six installed hashes and four untouched Raven art and
compass hashes. Installed parser readback found 53 unchanged Raven map rows,
53 unchanged Raven coordinate rows, and all 88 new Nornir IDs without overlap.

The first operation
`build/nornir-stock-family-test/backups/847323c4ec0849c6ac5627aee02cfb51/operation.json`
was rolled back for the later art test. The equivalent stock base was installed
again under
`build/nornir-stock-family-test/backups/998e51a12ac5461dbea27e7f07027572/operation.json`.
The checkpoint map Lua overlays above that stock base have their own journals.

Live screenshots `Screenshot 2026-09-25 145721.png` and
`Screenshot 2026-09-25 145742.png` show the tracked chest with the blue side
quest symbol and the tracked seal with the purple Valkyrie symbol on the
compass and in-world marker. Neither has the dock flag. The previous 14:47:55
map screenshot confirmed separate Nornir pins and restored Raven art. Bell and
mechanism compass art and the chest-opening clear still need live checks.
These are stock game symbols, so they do not represent final Nornir art.
Unloaded opened-chest state remains unresolved; production generation stays
blocked.
