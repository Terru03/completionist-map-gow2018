Completionist Map v0.10.0
CUSTOM ICON PIPELINE + RENDERING DISCOVERY

Base
----
v0.10.0 is built from the field-proven v0.9.6.1 behaviour:
- Raven map lifecycle
- Nornir parent + remaining puzzle children
- direct-XYZ custom HUD compass target
- custom filters
- Hide/Show Kratos with hidden-player opening centring
- MaxIn=2.5
- magnetic map cursor snapping disabled
- no synthetic game.Compass.ShowMarker()

User-authored concept PNGs
-------------------------
At install time the build uses your authenticated GitHub CLI session to fetch
ALL concept PNG masters from:

  Terru03/completionist-map-gow2018
  feat/completionist-icon-system
  assets/icons/concepts/

Families staged:
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

Files are stored under:

  GodOfWar\mods\completionist-map\icons\concepts

and transparent 24/32/48/64 px production candidates are generated under:

  GodOfWar\mods\completionist-map\icons\generated\<size>

A SHA256/dimension manifest is written to:

  GodOfWar\mods\completionist-map\icons\manifest.json

Rendering test
--------------
God of War's exposed Lua UI API is known to support authored material swaps,
but no loose-PNG binding API has yet been proven.

v0.10.0 therefore probes the SAFE synthetic Raven/Nornir map duplicates for:

  SetTexture
  SetTextureName
  SetImage
  SetImagePath
  SetSprite
  SetMaterialSwap

If an obvious direct texture/image setter exists, v0.10.0 tries the staged 32 px
PNG under pcall on that synthetic duplicate only.

If none exists, the marker remains the stable DockPoint proxy. The important
result is the ICON_CAPS / ICON_BIND_* log, which tells us whether we can bind
loose PNGs directly or must move to the game's authored material/texpack path.

The HUD proof carrier is only capability-probed in this build. Unknown image
setters are NOT invoked on the borrowed HUD object.

Install
-------
$zip = "$env:USERPROFILE\Downloads\Completionist-Map-v0.10.0-ICON-PIPELINE.zip"
$dir = "$env:TEMP\CompletionistMap-v100"

Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $zip -DestinationPath $dir -Force
powershell -ExecutionPolicy Bypass -File "$dir\install.ps1"

Fully restart God of War.

Test
----
1. Installer must download all ten concept masters and print dimensions/SHA256.
2. Open the same Midgard/Veithurgard test save.
3. Verify Raven and Nornir behaviour is unchanged.
4. Look at Raven, Nornir Chest and Seal artwork:
   - if a direct PNG setter exists, one or more may visibly switch to the custom art;
   - otherwise they deliberately remain DockPoint proxies for this build.
5. Test Add to Compass, filters and Hide/Show Kratos as regression checks.
6. Export the log below.

Log export
----------
$log = "G:\SteamLibrary\steamapps\common\GodOfWar\mods\loader_log.txt"
$out = "$env:USERPROFILE\Desktop\completionist-v100.txt"

$lines = Select-String $log -Pattern "CompletionistMap v0.10.0" |
    ForEach-Object { $_.Line }

@(
    "=== Completionist Map v0.10.0 ==="
    "Matches: $($lines.Count)"
    ""
    $lines
) | Set-Content $out

Get-Content $out

Most useful new lines
---------------------
ICON_CAPS
ICON_BIND_ATTEMPT
ICON_BIND_RESULT
HUD_ICON_CAPS

Regression lines
----------------
MAP_SCRIPT_LOADED
FILTER_MAPPING
MAP_PIN_CREATE
NORNIR_CHEST_PIN
NORNIR_PIN_CREATE
NORNIR_CHEST_COMPASS
NORNIR_COMPASS
CUSTOM_COMPASS
PLAYER_HIDDEN_CENTER

Safety
------
No Map.ChangeMarkerState().
No synthetic game.Compass.ShowMarker().
No puzzle/quest progression mutation.
No synthetic save writes.
Unknown texture methods are attempted only on synthetic map duplicates and only
when the method is actually present.
