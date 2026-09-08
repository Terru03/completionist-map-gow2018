param(
    [ValidateSet('Install','Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}

if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the Raven HUD instance probe.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
if (-not (Test-Path -LiteralPath $game -PathType Container)) {
    throw "God of War root not found: $game"
}

$target = Join-Path $game 'mods\lua\gameart\ui\scripts\hud\mainhud.lua'
$snippetPath = Join-Path $PSScriptRoot 'raven-hud-instance-probe.lua'
$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-hud-instance-probe'
$backupDir = Join-Path $stateDir 'backup'
$backup = Join-Path $backupDir 'mainhud.lua'
$manifest = Join-Path $stateDir 'active.json'
$beginMarker = '-- BEGIN COMPLETIONIST V0.10.4 RAVEN HUD INSTANCE PROBE'
$endMarker = '-- END COMPLETIONIST V0.10.4 RAVEN HUD INSTANCE PROBE'
$anchor = '  self.compassRadius = util.GetUiObjByName("Compass_Radius")'
$utf8 = New-Object Text.UTF8Encoding($false)

function Hash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Restore-Exact([string]$Target, [string]$Backup, [string]$Before, [string]$After) {
    if (-not (Test-Path -LiteralPath $Backup -PathType Leaf)) {
        throw "Missing backup: $Backup"
    }
    if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
        throw "Missing target: $Target"
    }

    $current = Hash $Target
    if ($current -ne $Before -and $current -ne $After) {
        throw 'mainhud.lua changed after probe installation. Refusing automatic overwrite.'
    }

    if ($current -ne $Before) {
        Copy-Item -LiteralPath $Backup -Destination $Target -Force
    }
    if ((Hash $Target) -ne $Before) {
        throw 'Rollback hash mismatch for mainhud.lua.'
    }
}

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        Write-Host 'Raven HUD instance probe is already removed.'
        return
    }

    $m = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    Restore-Exact $target $backup ([string]$m.mainhud_before) ([string]$m.mainhud_after)

    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifest -Destination $removed

    Write-Host 'Raven HUD instance probe removed.'
    Write-Host 'mainhud.lua restored exactly to its pre-probe hash.'
    return
}

if (Test-Path -LiteralPath $manifest -PathType Leaf) {
    throw 'Raven HUD instance probe is already installed.'
}
foreach ($required in @($target, $snippetPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing required file: $required"
    }
}

$text = [IO.File]::ReadAllText($target)
if ($text.Contains($beginMarker) -or $text.Contains($endMarker)) {
    throw 'Raven HUD instance probe markers already exist in mainhud.lua.'
}

$first = $text.IndexOf($anchor, [StringComparison]::Ordinal)
if ($first -lt 0) {
    throw 'Could not locate the expected MainHUD compassRadius setup anchor.'
}
$second = $text.IndexOf($anchor, $first + $anchor.Length, [StringComparison]::Ordinal)
if ($second -ge 0) {
    throw 'Found more than one MainHUD compassRadius setup anchor. Refusing ambiguous injection.'
}

$snippet = [IO.File]::ReadAllText($snippetPath).Trim()
if (-not $snippet.Contains($beginMarker) -or -not $snippet.Contains($endMarker)) {
    throw 'Probe snippet is missing its safety markers.'
}
if ($snippet.Contains('game.Compass.ShowMarker') -or
    $snippet.Contains('game.Compass.HideMarker') -or
    $snippet.Contains(':SetWorldPosition(') -or
    $snippet.Contains(':SetMaterialSwap(') -or
    $snippet.Contains(':Hide()') -or
    $snippet.Contains(':Show()')) {
    throw 'Probe snippet failed read-only source safety check.'
}

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item -LiteralPath $target -Destination $backup -Force
$before = Hash $target
if ((Hash $backup) -ne $before) {
    throw 'mainhud.lua backup hash mismatch.'
}

try {
    $replacement = $anchor + "`r`n" + $snippet
    $patched = $text.Substring(0, $first) + $replacement + $text.Substring($first + $anchor.Length)
    [IO.File]::WriteAllText($target, $patched, $utf8)

    $after = Hash $target
    if ($after -eq $before) {
        throw 'mainhud.lua did not change after probe injection.'
    }

    $verify = [IO.File]::ReadAllText($target)
    if (-not $verify.Contains($beginMarker) -or -not $verify.Contains($endMarker)) {
        throw 'Probe markers missing after mainhud.lua write.'
    }

    $m = [ordered]@{
        proof = 'v0.10.4 read-only Raven HUD instance inventory'
        branch = $branch
        mainhud_before = $before
        mainhud_after = $after
        backup = $backup
        installed_utc = [DateTime]::UtcNow.ToString('o')
        read_only = $true
        calls_show_marker = $false
        calls_hide_marker = $false
        moves_game_objects = $false
        writes_materials = $false
        writes_save_or_progression = $false
    }
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    [IO.File]::WriteAllText($manifest, ($m | ConvertTo-Json -Depth 8) + [Environment]::NewLine, $utf8)
}
catch {
    Write-Warning "Probe installation failed. Restoring mainhud.lua: $($_.Exception.Message)"
    try {
        Copy-Item -LiteralPath $backup -Destination $target -Force
    }
    catch {
        Write-Warning "Automatic recovery also failed: $($_.Exception.Message)"
    }
    throw
}

Write-Host ''
Write-Host 'Raven HUD instance probe installed.'
Write-Host '- read-only runtime inventory only'
Write-Host '- no Compass Show/Hide calls'
Write-Host '- no GameObject movement, visibility or material changes'
Write-Host '- no save/progression/marker-state writes'
Write-Host ''
Write-Host 'Launch God of War, load the Veithurgard test save, Add the Raven to Compass, return to gameplay for about 10 seconds, then run collect-raven-hud-instance-probe.ps1 while the game is still running.'
