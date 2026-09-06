param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

$relative = 'gameart\ui\scripts\inworldmenu\mapmenu.lua'
$dest = Join-Path $GameRoot ('mods\lua\' + $relative)
$backup = $dest + '.completionist-v061-backup'

if (Test-Path $backup) {
    Move-Item $backup $dest -Force
    Write-Host 'Restored the mapmenu override that existed before v0.6.1.'
    exit 0
}

if (Test-Path $dest) {
    $existing = [IO.File]::ReadAllText($dest)

    if ($existing.Contains('[CompletionistMap v0.6.1]')) {
        Remove-Item $dest -Force
        Write-Host 'Removed Completionist Map v0.6.1.'
    } else {
        Write-Host 'Existing mapmenu.lua is not v0.6.1. Nothing was removed.'
    }
} else {
    Write-Host 'Completionist Map v0.6.1 is not installed.'
}
