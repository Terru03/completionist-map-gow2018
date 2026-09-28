"""Build production-ready, universal Nexus Mods distribution package for Completionist Map.

Creates a standalone, 1-click installer and zip package compatible with:
1. Automated 1-click Install.bat / Uninstall.bat (PowerShell 5.1+ built into Windows 10/11)
2. Vortex / Mod Organizer 2 mod managers (standard archive root layout)
3. Manual drag-and-drop into God of War root folder
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist/nexus"
PKG_DIR = DIST / "CompletionistMap-v1.0.0"
SCREENSHOTS_SRC = Path(os.environ.get("GOW_SCREENSHOTS_DIR", Path.home() / "Pictures" / "Screenshots"))
_default_game = next(
    (p for p in [
        os.environ.get("GOW_GAME_DIR"),
        r"G:\SteamLibrary\steamapps\common\GodOfWar",
        r"C:\Program Files (x86)\Steam\steamapps\common\GodOfWar",
        r"D:\SteamLibrary\steamapps\common\GodOfWar",
    ] if p and Path(p).exists()),
    Path(".")
)
GAME_DIR = Path(_default_game)

MOD_FILES = [
    "dxgi.dll",
    "exec/dc/pc_le/mapcoords.dcb",
    "exec/dc/pc_le/mapmaster.dcb",
    "exec/dc/pc_le/wad_r_perm.dcb",
    "exec/dc/pc_le/wad_r_ui.dcb",
    "exec/patch/pc_le/completionist_v105_family_art.texpack",
    "exec/patch/pc_le/completionist_v105_family_art.texpack.toc",
    "exec/wad/pc_le/r_ui.wad",
    "mods/completionist-map/native/collectible-base-dxgi.dll",
    "mods/completionist-map/native/raven-native-bridge-manifest.json",
    "mods/lua/gameart/scripts/levels/gameplaymodules/interactive/triptychs/interact_triptych.lua",
    "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_runic.lua",
    "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua",
    "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_loot_artifact.lua",
    "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_loot_dirtdig.lua",
    "mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_loot_pocketrift.lua",
    "mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua",
    "mods/lua/gameart/scripts/levels/gameplaymodules/soninteracts/langcheckruneread.lua",
    "mods/lua/gameart/scripts/levels/gameplaymodules/soninteracts/sonlanguagepickup.lua",
    "mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua",
]

SCREENSHOT_MAP = [
    ("Screenshot 2026-09-28 141000.png", "01_map_overview_lake_of_nine.png"),
    ("Screenshot 2026-09-28 232429.png", "02_map_cluster_light_elf_outpost.png"),
    ("Screenshot 2026-09-28 141102.png", "03_compass_hud_in_world.png"),
    ("Screenshot 2026-09-28 081207.png", "04_thamurs_corpse_reticle_pin.png"),
    ("Screenshot 2026-09-28 092525.png", "05_fog_of_war_reveal_wildwoods.png"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


INSTALL_PS1 = r"""<#
.SYNOPSIS
    Universal 1-Click Installer for God of War (2018) Completionist Map Mod.
.DESCRIPTION
    Auto-detects God of War install folder across Steam, Epic Games, custom drives,
    or user prompt. Safely backs up stock game files before copying mod files.
#>
param(
    [string]$TargetDir = ""
)

$ErrorActionPreference = "Stop"

function Find-GodOfWar {
    # 1. TargetDir parameter
    if ($TargetDir -and (Test-Path (Join-Path $TargetDir "GoW.exe"))) {
        return (Resolve-Path $TargetDir).Path
    }
    # 2. Parent directory of script / current directory (if extracted directly into game folder)
    $scriptDir = Split-Path -Parent $PSScriptRoot
    if (Test-Path (Join-Path $scriptDir "GoW.exe")) {
        return $scriptDir
    }
    $currDir = (Get-Location).Path
    if (Test-Path (Join-Path $currDir "GoW.exe")) {
        return $currDir
    }
    # 3. Steam Registry (32-bit & 64-bit)
    $regPaths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 1593500",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 1593500"
    )
    foreach ($reg in $regPaths) {
        if (Test-Path $reg) {
            $loc = (Get-ItemProperty $reg -ErrorAction SilentlyContinue).InstallLocation
            if ($loc -and (Test-Path (Join-Path $loc "GoW.exe"))) {
                return $loc
            }
        }
    }
    # 4. Steam libraryfolders.vdf parser
    $steamReg = Get-ItemProperty "HKCU:\SOFTWARE\Valve\Steam" -ErrorAction SilentlyContinue
    if ($steamReg -and $steamReg.SteamPath) {
        $vdf = Join-Path $steamReg.SteamPath "steamapps\libraryfolders.vdf"
        if (Test-Path $vdf) {
            $content = Get-Content $vdf -Raw -ErrorAction SilentlyContinue
            $matches = [regex]::Matches($content, '"path"\s+"([^"]+)"')
            foreach ($m in $matches) {
                $libPath = $m.Groups[1].Value.Replace('\\', '\')
                $testPath = Join-Path $libPath "steamapps\common\GodOfWar"
                if (Test-Path (Join-Path $testPath "GoW.exe")) {
                    return $testPath
                }
            }
        }
    }
    # 5. Epic Games Manifests
    $epicDir = "C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
    if (Test-Path $epicDir) {
        Get-ChildItem $epicDir -Filter "*.item" -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $json = Get-Content $_.FullName -Raw | ConvertFrom-Json
                if ($json.DisplayName -match "God of War" -and (Test-Path (Join-Path $json.InstallLocation "GoW.exe"))) {
                    return $json.InstallLocation
                }
            } catch {}
        }
    }
    # 6. Common Library Paths across drives C: through H:
    $drives = Get-PSDrive -PSProvider FileSystem | Select-Object -ExpandProperty Root
    $subpaths = @(
        "Program Files (x86)\Steam\steamapps\common\GodOfWar",
        "Program Files\Steam\steamapps\common\GodOfWar",
        "SteamLibrary\steamapps\common\GodOfWar",
        "Steam\steamapps\common\GodOfWar",
        "Games\GodOfWar",
        "Epic Games\GodOfWar"
    )
    foreach ($d in $drives) {
        foreach ($sub in $subpaths) {
            $candidate = Join-Path $d $sub
            if (Test-Path (Join-Path $candidate "GoW.exe")) {
                return $candidate
            }
        }
    }
    # 7. Interactive Folder Browser fallback
    Write-Host "God of War installation directory not detected automatically." -ForegroundColor Yellow
    Write-Host "Please select your God of War game directory in the window (where GoW.exe is located)..." -ForegroundColor Cyan
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Select your God of War game folder (contains GoW.exe)"
    $dialog.ShowNewFolderButton = $false
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        if (Test-Path (Join-Path $dialog.SelectedPath "GoW.exe")) {
            return $dialog.SelectedPath
        } else {
            Write-Host "ERROR: The selected folder does not contain GoW.exe!" -ForegroundColor Red
        }
    }
    return $null
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "   God of War (2018) - Completionist Map Mod Installer  " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# Check if GoW is running
$gowProc = Get-Process "GoW" -ErrorAction SilentlyContinue
if ($gowProc) {
    Write-Host "WARNING: God of War is currently running!" -ForegroundColor Red
    Write-Host "Please close the game before proceeding with installation." -ForegroundColor Yellow
    Write-Host "Press any key to retry after closing the game..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    $gowProc = Get-Process "GoW" -ErrorAction SilentlyContinue
    if ($gowProc) {
        Write-Host "God of War is still running. Aborting installation." -ForegroundColor Red
        exit 1
    }
}

$game = Find-GodOfWar
if (-not $game) {
    Write-Host "ERROR: God of War installation folder could not be found." -ForegroundColor Red
    Write-Host "Please place the installer folder directly inside your God of War game folder and run Install.bat again." -ForegroundColor Yellow
    exit 1
}

Write-Host "[+] Detected God of War at: $game" -ForegroundColor Green

$sourceRoot = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $sourceRoot "manifest.json"
if (-not (Test-Path $manifestPath)) {
    Write-Host "ERROR: manifest.json missing from installer package." -ForegroundColor Red
    exit 1
}
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json

# Prepare Backup directory
$backupDir = Join-Path $game "completionist_backup"
$backupManifest = Join-Path $backupDir "backup_manifest.json"
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
}

$backedUp = @{}
if (Test-Path $backupManifest) {
    Write-Host "[i] Existing stock backup found in completionist_backup. Preserving original backup." -ForegroundColor Yellow
} else {
    Write-Host "[*] Creating safe backup of stock game files..." -ForegroundColor Cyan
    foreach ($rel in $manifest.files.PSObject.Properties.Name) {
        $target = Join-Path $game $rel
        if (Test-Path $target) {
            $dest = Join-Path $backupDir $rel
            $destParent = Split-Path -Parent $dest
            if (-not (Test-Path $destParent)) {
                New-Item -ItemType Directory -Force -Path $destParent | Out-Null
            }
            Copy-Item -Path $target -Destination $dest -Force
            $backedUp[$rel] = (Get-FileHash -Path $target -Algorithm SHA256).Hash.ToLower()
        }
    }
    # Also backup boot-options.json
    $bootPath = Join-Path $game "exec\boot-options.json"
    if (Test-Path $bootPath) {
        $destBoot = Join-Path $backupDir "exec\boot-options.json"
        $destBootParent = Split-Path -Parent $destBoot
        if (-not (Test-Path $destBootParent)) { New-Item -ItemType Directory -Force -Path $destBootParent | Out-Null }
        Copy-Item -Path $bootPath -Destination $destBoot -Force
        $backedUp["exec/boot-options.json"] = (Get-FileHash -Path $bootPath -Algorithm SHA256).Hash.ToLower()
    }

    $backupInfo = @{
        "created_at" = (Get-Date).ToString("o")
        "files" = $backedUp
    }
    $backupInfo | ConvertTo-Json -Depth 5 | Set-Content -Path $backupManifest -Encoding UTF8
    Write-Host "[+] Backed up $(($backedUp.Keys).Count) stock files to completionist_backup." -ForegroundColor Green
}

# Copy mod files
Write-Host "[*] Installing Completionist Map mod files..." -ForegroundColor Cyan
$installCount = 0
foreach ($rel in $manifest.files.PSObject.Properties.Name) {
    $src = Join-Path $sourceRoot $rel
    if (-not (Test-Path $src)) {
        Write-Host "ERROR: Package file missing: $rel" -ForegroundColor Red
        exit 1
    }
    $dest = Join-Path $game $rel
    $destParent = Split-Path -Parent $dest
    if (-not (Test-Path $destParent)) {
        New-Item -ItemType Directory -Force -Path $destParent | Out-Null
    }
    Copy-Item -Path $src -Destination $dest -Force
    $installCount++
}

# Update boot-options.json for family art texpack
$bootPath = Join-Path $game "exec\boot-options.json"
if (Test-Path $bootPath) {
    try {
        $boot = Get-Content $bootPath -Raw | ConvertFrom-Json
        $entry = "../../patch/pc_le/completionist_v105_family_art"
        $packs = [System.Collections.ArrayList]@($boot.'patch-texpacks')
        if (-not $packs.Contains($entry)) {
            $packs.Add($entry) | Out-Null
            $boot.'patch-texpacks' = $packs
            $boot | ConvertTo-Json -Depth 5 | Set-Content -Path $bootPath -Encoding UTF8
            Write-Host "[+] Registered artwork patch texpack in boot-options.json" -ForegroundColor Green
        }
    } catch {
        Write-Host "WARNING: Could not update boot-options.json automatically: $_" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "           INSTALLATION COMPLETED SUCCESSFULLY!         " -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host " Features active:" -ForegroundColor Cyan
Write-Host "  * 498 collectibles across all 15 families on map"
Write-Host "  * All 54 Odin's Ravens with native authority & tracking"
Write-Host "  * Chest state persistence across restarts (wooden chests, etc.)"
Write-Host "  * Custom map markers & compass HUD icons with distance meters"
Write-Host "  * In-map [Down Arrow] toggle button (Hide / Show Markers)"
Write-Host "  * Original stock files backed up to: completionist_backup"
Write-Host ""
Write-Host "You can now launch God of War!" -ForegroundColor Cyan
exit 0
"""

UNINSTALL_PS1 = r"""<#
.SYNOPSIS
    Universal 1-Click Uninstaller for God of War (2018) Completionist Map Mod.
.DESCRIPTION
    Restores original stock files from completionist_backup and cleans up added mod files.
#>
param(
    [string]$TargetDir = ""
)

$ErrorActionPreference = "Stop"

function Find-GodOfWar {
    if ($TargetDir -and (Test-Path (Join-Path $TargetDir "GoW.exe"))) {
        return (Resolve-Path $TargetDir).Path
    }
    $scriptDir = Split-Path -Parent $PSScriptRoot
    if (Test-Path (Join-Path $scriptDir "GoW.exe")) {
        return $scriptDir
    }
    $currDir = (Get-Location).Path
    if (Test-Path (Join-Path $currDir "GoW.exe")) {
        return $currDir
    }
    $regPaths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 1593500",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 1593500"
    )
    foreach ($reg in $regPaths) {
        if (Test-Path $reg) {
            $loc = (Get-ItemProperty $reg -ErrorAction SilentlyContinue).InstallLocation
            if ($loc -and (Test-Path (Join-Path $loc "GoW.exe"))) {
                return $loc
            }
        }
    }
    $steamReg = Get-ItemProperty "HKCU:\SOFTWARE\Valve\Steam" -ErrorAction SilentlyContinue
    if ($steamReg -and $steamReg.SteamPath) {
        $vdf = Join-Path $steamReg.SteamPath "steamapps\libraryfolders.vdf"
        if (Test-Path $vdf) {
            $content = Get-Content $vdf -Raw -ErrorAction SilentlyContinue
            $matches = [regex]::Matches($content, '"path"\s+"([^"]+)"')
            foreach ($m in $matches) {
                $libPath = $m.Groups[1].Value.Replace('\\', '\')
                $testPath = Join-Path $libPath "steamapps\common\GodOfWar"
                if (Test-Path (Join-Path $testPath "GoW.exe")) {
                    return $testPath
                }
            }
        }
    }
    $drives = Get-PSDrive -PSProvider FileSystem | Select-Object -ExpandProperty Root
    $subpaths = @(
        "Program Files (x86)\Steam\steamapps\common\GodOfWar",
        "Program Files\Steam\steamapps\common\GodOfWar",
        "SteamLibrary\steamapps\common\GodOfWar",
        "Steam\steamapps\common\GodOfWar",
        "Games\GodOfWar",
        "Epic Games\GodOfWar"
    )
    foreach ($d in $drives) {
        foreach ($sub in $subpaths) {
            $candidate = Join-Path $d $sub
            if (Test-Path (Join-Path $candidate "GoW.exe")) {
                return $candidate
            }
        }
    }
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Select your God of War game folder to uninstall mod"
    $dialog.ShowNewFolderButton = $false
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        if (Test-Path (Join-Path $dialog.SelectedPath "GoW.exe")) {
            return $dialog.SelectedPath
        }
    }
    return $null
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  God of War (2018) - Completionist Map Mod Uninstaller " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$gowProc = Get-Process "GoW" -ErrorAction SilentlyContinue
if ($gowProc) {
    Write-Host "WARNING: God of War is currently running!" -ForegroundColor Red
    Write-Host "Please close the game before uninstalling the mod." -ForegroundColor Yellow
    exit 1
}

$game = Find-GodOfWar
if (-not $game) {
    Write-Host "ERROR: God of War installation folder could not be found." -ForegroundColor Red
    exit 1
}

$backupDir = Join-Path $game "completionist_backup"
$backupManifest = Join-Path $backupDir "backup_manifest.json"

if (-not (Test-Path $backupManifest)) {
    Write-Host "ERROR: No backup found in: $backupDir" -ForegroundColor Red
    Write-Host "Cannot restore automatically without backup manifest." -ForegroundColor Yellow
    exit 1
}

$manifest = Get-Content $backupManifest -Raw | ConvertFrom-Json
Write-Host "[*] Restoring original stock game files from backup..." -ForegroundColor Cyan

foreach ($rel in $manifest.files.PSObject.Properties.Name) {
    $src = Join-Path $backupDir $rel
    $dest = Join-Path $game $rel
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $dest -Force
        Write-Host "  Restored: $rel" -ForegroundColor Gray
    }
}

# Clean added files
$addedFiles = @(
    "exec\patch\pc_le\completionist_v105_family_art.texpack",
    "exec\patch\pc_le\completionist_v105_family_art.texpack.toc",
    "mods\completionist-map\native\collectible-base-dxgi.dll",
    "mods\completionist-map\native\raven-native-bridge-manifest.json",
    "mods\completionist-map\native\raven-native-bridge.log"
)
foreach ($rel in $addedFiles) {
    $target = Join-Path $game $rel
    if (Test-Path $target) {
        Remove-Item -Path $target -Force -ErrorAction SilentlyContinue
        Write-Host "  Removed mod file: $rel" -ForegroundColor Gray
    }
}

# Clean boot-options.json
$bootPath = Join-Path $game "exec\boot-options.json"
if (Test-Path $bootPath) {
    try {
        $boot = Get-Content $bootPath -Raw | ConvertFrom-Json
        $entry = "../../patch/pc_le/completionist_v105_family_art"
        $packs = [System.Collections.ArrayList]@($boot.'patch-texpacks')
        if ($packs.Contains($entry)) {
            $packs.Remove($entry)
            $boot.'patch-texpacks' = $packs
            $boot | ConvertTo-Json -Depth 5 | Set-Content -Path $bootPath -Encoding UTF8
            Write-Host "  Cleaned texpack entry from boot-options.json" -ForegroundColor Gray
        }
    } catch {}
}

# Remove backup directory
Remove-Item -Path $backupDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "         UNINSTALLATION COMPLETED SUCCESSFULLY!         " -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host "Original stock files have been restored." -ForegroundColor Cyan
Write-Host "All mod-added files have been cleaned up." -ForegroundColor Cyan
exit 0
"""

INSTALL_BAT = r"""@echo off
setlocal
cd /d "%~dp0"
echo ========================================================
echo   God of War (2018) - Completionist Map Mod Installer
echo ========================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Installation did not finish successfully (exit code %ERRORLEVEL%).
    pause
    exit /b %ERRORLEVEL%
)
echo.
pause
"""

UNINSTALL_BAT = r"""@echo off
setlocal
cd /d "%~dp0"
echo ========================================================
echo   God of War (2018) - Completionist Map Mod Uninstaller
echo ========================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall.ps1" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Uninstallation did not finish successfully (exit code %ERRORLEVEL%).
    pause
    exit /b %ERRORLEVEL%
)
echo.
pause
"""

README_TXT = r"""================================================================================
           GOD OF WAR (2018) PC - COMPLETIONIST MAP MOD v1.0.0
================================================================================

All 498 collectibles across all 15 families tracked on your in-game Map & Compass.

--------------------------------------------------------------------------------
1. FEATURES
--------------------------------------------------------------------------------
- Full 15-Family Collectible Coverage (498 markers total across all realms):
    * Odin's Ravens (all 54 in Midgard & realms with live dead-state authority)
    * Nornir Chests (all 22)
    * Legendary Chests (all 26)
    * Wooden / Coffin Chests (259 locations with permanent saved-state tracking)
    * Artefacts (all 45 across 7 sets)
    * Jötnar Shrines (all 11)
    * Lore Markers (all 39)
    * Lore Scrolls (all 33)
    * Realm Tears (all 18)
    * Treasure Maps & Buried Treasures (all 12 pairs)
    * Valkyries (all 9)
    * Nornir Bells, Mechanisms & Rune Seals
- Custom Map Marker Artwork: Unique, lore-friendly icon for every collectible type.
- Custom Compass HUD Artwork: Full compass icons and distance tracking in 3D world.
- On-Screen Toggle: Press [Down Arrow] anytime on the map to Show/Hide markers.
  Your choice persists across map opens.
- Single Reticle Lock: Press [Enter] / [E] to pin any marker to the compass HUD.
- Zero Desync: Native C++ authority bridge prevents marker revival on load.

--------------------------------------------------------------------------------
2. REQUIREMENTS
--------------------------------------------------------------------------------
- God of War (2018) on PC (Steam or Epic Games Store, patch 1.0.12 or newer).
- GoW Script Loader & Gameplay Tweaks 0.22 (or compatible dinput8/dxgi loader).

--------------------------------------------------------------------------------
3. INSTALLATION
--------------------------------------------------------------------------------
OPTION A: Automated 1-Click Installer (Recommended)
1. Extract this zip file anywhere.
2. Double-click "Install.bat".
   The installer automatically detects your God of War folder (Steam/Epic),
   backs up your original stock files, and installs the mod.
3. Launch God of War and open your map!

OPTION B: Mod Managers (Vortex / MO2)
1. Drag and drop this zip file into Vortex / Mod Organizer 2.
2. Enable and Deploy.

OPTION C: Manual Installation
1. Copy the contents of this zip (dxgi.dll, exec\, mods\) into your God of War
   game folder (where GoW.exe is located).
2. Ensure GoW Script Loader 0.22 is installed.

--------------------------------------------------------------------------------
4. UNINSTALLATION
--------------------------------------------------------------------------------
- If you used the installer: Double-click "Uninstall.bat".
  It will restore your original stock files from backup and clean up mod files.
- If you installed via Vortex / MO2: Disable and Undeploy in your mod manager.
- If manual: Restore your backed-up files or verify file integrity via Steam/Epic.

================================================================================
Created with care for the God of War PC community. Enjoy your 100% journey!
================================================================================
"""


def build():
    print(f"[*] Packaging Completionist Map for Nexus Mods...")
    if PKG_DIR.exists():
        shutil.rmtree(PKG_DIR)
    PKG_DIR.mkdir(parents=True)

    files_manifest = {}

    for rel in MOD_FILES:
        src = GAME_DIR / rel
        if not src.is_file():
            raise FileNotFoundError(f"Required mod file missing from game: {src}")
        dest = PKG_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        files_manifest[rel] = {
            "size": dest.stat().st_size,
            "sha256": sha256(dest)
        }
        print(f"  [+] {rel} ({dest.stat().st_size:,} bytes)")

    # Scripts & Launchers
    scripts_dir = PKG_DIR / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "install.ps1").write_text(INSTALL_PS1.strip() + "\n", encoding="utf-8")
    (scripts_dir / "uninstall.ps1").write_text(UNINSTALL_PS1.strip() + "\n", encoding="utf-8")
    (PKG_DIR / "Install.bat").write_text(INSTALL_BAT.strip() + "\r\n", encoding="utf-8")
    (PKG_DIR / "Uninstall.bat").write_text(UNINSTALL_BAT.strip() + "\r\n", encoding="utf-8")
    (PKG_DIR / "README.txt").write_text(README_TXT.strip() + "\r\n", encoding="utf-8")

    # Manifest
    manifest_data = {
        "name": "God of War Completionist Map",
        "version": "1.0.0",
        "author": "Terru03",
        "nexus_mod_id": 396,
        "files": files_manifest
    }
    (PKG_DIR / "manifest.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    # Create Screenshots Directory
    screenshots_dist = DIST / "screenshots"
    screenshots_dist.mkdir(parents=True, exist_ok=True)
    for src_name, dst_name in SCREENSHOT_MAP:
        src_path = SCREENSHOTS_SRC / src_name
        if src_path.is_file():
            shutil.copy2(src_path, screenshots_dist / dst_name)
            print(f"  [+] Screenshot: {dst_name}")

    # Create ZIP archive
    zip_path = DIST / "CompletionistMap-v1.0.0.zip"
    print(f"[*] Compressing into {zip_path}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in PKG_DIR.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(PKG_DIR).as_posix()
                zf.write(file, arcname)

    print(f"[+] Package created successfully!")
    print(f"    Folder: {PKG_DIR}")
    print(f"    Zip:    {zip_path} ({zip_path.stat().st_size:,} bytes)")
    print(f"    Screenshots: {screenshots_dist}")
    return zip_path


if __name__ == "__main__":
    build()
