param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)
$ErrorActionPreference = 'Stop'

$items = @(
    @{
        Relative = 'gameart\ui\scripts\inworldmenu\mapmenu.lua'
        BackupSuffix = '.pre-v100-backup'
    },
    @{
        Relative = 'gameart\ui\scripts\hud\mainhud.lua'
        BackupSuffix = '.pre-v100-backup'
    },
    @{
        Relative = 'gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
        BackupSuffix = '.pre-v100-backup'
    },
    @{
        Relative = 'gameart\scripts\levels\gameplaymodules\progression\interact_chest_runic.lua'
        BackupSuffix = '.pre-v100-backup'
    },
    @{
        Relative = 'gameart\scripts\levels\gameplaymodules\progression\interact_chest_standard.lua'
        BackupSuffix = '.pre-v100-backup'
    }
)

foreach ($item in $items) {
    $dest = Join-Path $GameRoot ('mods\lua\' + $item.Relative)
    $backup = $dest + $item.BackupSuffix

    if (Test-Path $backup) {
        Copy-Item $backup $dest -Force
        Remove-Item $backup -Force
        Write-Host "Restored: $dest"
        continue
    }

    if (Test-Path $dest) {
        $text = [IO.File]::ReadAllText($dest)
        if ($text.Contains('[CompletionistMap v0.10.1]') -or
            $text.Contains('[CompletionistMap v0.10.0]')) {
            Remove-Item $dest -Force
            Write-Host "Removed Completionist v0.10.x override: $dest"
        }
    }
}

$iconRoot = Join-Path $GameRoot 'mods\completionist-map\icons'
if (Test-Path $iconRoot) {
    Remove-Item $iconRoot -Recurse -Force
    Write-Host "Removed icon staging tree: $iconRoot"
}
