param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

$relative = 'gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$dest = Join-Path $GameRoot ('mods\lua\' + $relative)
$backup = $dest + '.completionist-v051-backup'

if (Test-Path $backup) {
    Move-Item $backup $dest -Force
    Write-Host 'Restored the precisionchallenge.lua override that existed before v0.5.1.'
    exit 0
}

if (Test-Path $dest) {
    $existing = [IO.File]::ReadAllText($dest)

    if ($existing.Contains('[CompletionistMap v0.5.1]')) {
        Remove-Item $dest -Force
        Write-Host 'Removed Completionist Map v0.5.1 raven diagnostic.'
    } else {
        Write-Host 'Existing precisionchallenge.lua is not the v0.5.1 diagnostic. Nothing was removed.'
    }
} else {
    Write-Host 'Completionist Map v0.5.1 raven diagnostic is not installed.'
}
