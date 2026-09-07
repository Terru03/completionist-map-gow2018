Completionist Map v0.10.1
LOCAL ICON PACKAGE + RENDERING DISCOVERY

Base
----
v0.10.1 keeps the field-proven v0.9.6.1 behaviour and the v0.10.0 runtime
icon-capability probes. The only intended functional change from v0.10.0 is
how the user-authored icon masters reach the installer.

Retained behaviour:
- Raven map lifecycle
- Nornir parent + remaining puzzle children
- direct-XYZ custom HUD compass target
- custom filters
- Hide/Show Kratos with hidden-player opening centring
- MaxIn=2.5
- magnetic map cursor snapping disabled
- no synthetic game.Compass.ShowMarker()

Local/bundled concept PNGs
--------------------------
The installer no longer uses GitHub, gh, tokens, private raw URLs or the
feat/completionist-icon-system branch.

The test ZIP bundles all ten concept PNG masters under:

  assets\icons\concepts\

When install.ps1 is run directly from the cloned repository it instead falls
back to the repository's own:

  assets\icons\concepts\

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

At install time each PNG signature is validated, copied to:

  GodOfWar\mods\completionist-map\icons\concepts

and transparent 24/32/48/64 px production candidates are generated under:

  GodOfWar\mods\completionist-map\icons\generated\<size>

A SHA256/dimension manifest is written to:

  GodOfWar\mods\completionist-map\icons\manifest.json

Rendering test
--------------
God of War's exposed Lua UI API is known to support authored material swaps,
but no loose-PNG binding API has yet been proven.

v0.10.1 therefore retains the safe v0.10.0 probes on synthetic Raven/Nornir
map duplicates for:

  SetTexture
  SetTextureName
  SetImage
  SetImagePath
  SetSprite
  SetMaterialSwap

If an obvious direct texture/image setter exists, the staged 32 px PNG is tried
under pcall on that synthetic duplicate only.

If none exists, the marker remains the stable DockPoint proxy. ICON_CAPS and
ICON_BIND_* tell us whether loose PNGs can be bound directly or whether the
next step must use the game's authored material/texpack path.

The HUD proof carrier is capability-probed only. Unknown image setters are not
invoked on the borrowed HUD object.

Build from the cloned repo
--------------------------
powershell -ExecutionPolicy Bypass -File ".\tools\v0.10.1\prepare-local-retry.ps1"
powershell -ExecutionPolicy Bypass -File ".\tools\v0.10.1\build-package.ps1"

Output:

  dist\Completionist-Map-v0.10.1-LOCAL-ICONS.zip

Install test ZIP
----------------
$zip = "$env:USERPROFILE\Documents\GitHub\completionist-map-gow2018\dist\Completionist-Map-v0.10.1-LOCAL-ICONS.zip"
$dir = "$env:TEMP\CompletionistMap-v101"

Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $zip -DestinationPath $dir -Force
powershell -ExecutionPolicy Bypass -File "$dir\install.ps1"

Fully restart God of War.

Test
----
1. Installer must stage all ten local/bundled concept masters without any
   GitHub request and print dimensions/SHA256.
2. Open the same Midgard/Veithurgard test save.
3. Verify Raven and Nornir behaviour is unchanged.
4. Check Raven, Nornir Chest and Seal artwork:
   - if a direct PNG setter exists, one or more may visibly switch to custom art;
   - otherwise they deliberately remain DockPoint proxies for this build.
5. Test Add to Compass, filters and Hide/Show Kratos as regression checks.
6. Export the log below.

Log export
----------
$log = "G:\SteamLibrary\steamapps\common\GodOfWar\mods\loader_log.txt"
$out = "$env:USERPROFILE\Desktop\completionist-v101.txt"

$lines = Select-String $log -Pattern "CompletionistMap v0.10.1" |
    ForEach-Object { $_.Line }

@(
    "=== Completionist Map v0.10.1 ==="
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
