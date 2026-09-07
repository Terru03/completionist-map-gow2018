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

Player marker invariant
-----------------------
The Kratos/player map marker must remain the game's native Omega marker.
Completionist Map may hide/show that native marker, but must not replace its
artwork or material. player_marker_concept_master.png is a design/reference
asset only and is not a runtime replacement target.

Local/bundled concept PNGs
--------------------------
The installer no longer uses GitHub, gh, tokens, private raw URLs or the
feat/completionist-icon-system branch.

The test ZIP bundles all ten concept PNG masters under:

  assets\icons\concepts\

When install.ps1 is run directly from the cloned repository it instead falls
back to the repository's own:

  assets\icons\concepts\

Runtime collectible families staged/probed:
- Raven
- Nornir Chest
- Nornir Seal
- Nornir Bell
- Nornir Mechanism
- Lore Marker
- Artefact
- Legendary Chest
- Remaining Collectible

The Player Marker master is bundled only as a reference asset. The native
Kratos Omega marker remains untouched.

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

Observed v0.10.1 result
-----------------------
The Veithurgard field test showed SetTexture/SetImage/SetSprite are not exposed
on the synthetic map objects or UI helper. SetMaterialSwap is exposed. Raven,
Nornir Chest and Nornir Seal therefore correctly fell back to DockPoint visuals.
The next icon implementation path is authored material/MPIcon material swap,
not loose PNG binding.

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
1. Installer must stage all local/bundled concept masters without any GitHub
   request and print dimensions/SHA256.
2. Open the same Midgard/Veithurgard test save.
3. Verify Raven and Nornir behaviour is unchanged.
4. Check Raven, Nornir Chest and Seal artwork.
5. Confirm the Kratos player icon is still the native Omega marker.
6. Test Add to Compass, filters and Hide/Show Kratos as regression checks.
7. Export, commit and push the log with the helper below.

Log export + Git push
---------------------
From anywhere inside the cloned repository:

powershell -ExecutionPolicy Bypass -File ".\tools\export-field-log.ps1" -Version v0.10.1

The helper:
- reads GodOfWar\mods\loader_log.txt;
- writes archive\field-logs\completionist-v101.txt;
- stages only that field-log file;
- commits only that field-log file if it changed;
- pushes the current branch to origin.

This keeps field-test evidence available in GitHub for later analysis without a
manual Desktop upload or separate git add/commit/push sequence.

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
The native Kratos/Omega map marker artwork is never replaced.
Unknown texture methods are attempted only on synthetic map duplicates and only
when the method is actually present.
