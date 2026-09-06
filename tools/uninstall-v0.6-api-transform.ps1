param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

$relative = 'gameart\ui\scripts\inworldmenu\mapmenu.lua'
$dest = Join-Path $GameRoot ('mods\lua\' + $relative)
$backup = $dest + '.completionist-v06-backup'

if (Test-Path $backup) {
    Move-Item $backup $dest -Force
    Write-Host 'Restored the mapmenu override that existed before v0.6.'
    exit 0
}

if (Test-Path $dest) {
    $existing = [IO.File]::ReadAllText($dest)
    if ($existing.Contains('[CompletionistMap v0.6]')) {
        Remove-Item $dest -Force
        Write-Host 'Removed Completionist Map v0.6 mapmenu override.'
    } else {
        Write-Host 'Existing mapmenu.lua is not the v0.6 prototype. Nothing was removed.'
    }
} else {
    Write-Host 'Completionist Map v0.6 is not installed.'
}
