param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

$relative = 'gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$dest = Join-Path $GameRoot ('mods\lua\' + $relative)
$backup = $dest + '.completionist-v05-backup'

if (Test-Path $backup) {
    Move-Item $backup $dest -Force
    Write-Host 'Restored the pre-v0.5 precisionchallenge.lua override.'
} elseif (Test-Path $dest) {
    $existing = [IO.File]::ReadAllText($dest)
    if ($existing.Contains('[CompletionistMap v0.5]')) {
        Remove-Item $dest -Force
        Write-Host 'Removed the v0.5 precisionchallenge.lua override.'
    } else {
        Write-Host 'The existing precisionchallenge.lua does not look like the v0.5 diagnostic. Nothing was removed.'
    }
} else {
    Write-Host 'v0.5 raven diagnostic is not installed.'
}
