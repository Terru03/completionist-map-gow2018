param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}

$game = [IO.Path]::GetFullPath($GameRoot)
$log = Join-Path $game 'mods\loader_log.txt'
$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-hud-instance-probe'
$manifest = Join-Path $stateDir 'active.json'
$prefix = '[CompletionistMap v0.10.4-hud-probe]'
$reportRel = 'archive/field-logs/completionist-v104-raven-hud-instance-runtime.txt'
$report = Join-Path $repo ($reportRel -replace '/', '\')
$utf8 = New-Object Text.UTF8Encoding($false)

if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
    throw 'Raven HUD instance probe manifest is missing. Install the probe first.'
}
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
    throw "Loader log not found: $log"
}

$m = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
$matches = @(Select-String -LiteralPath $log -SimpleMatch $prefix | ForEach-Object { $_.Line })
if ($matches.Count -eq 0) {
    throw 'No Raven HUD instance-probe lines were found. Launch the game and exercise Add to Compass first.'
}

$hitLines = @($matches | Where-Object { $_ -like '* HIT *' })
$scanLines = @($matches | Where-Object { $_ -like '* SCAN_BEGIN *' })
$trackedLines = @($matches | Where-Object { $_ -like '*tracked=true*' })
$rootLines = @($matches | Where-Object { $_ -like '* ROOT *' -or $_ -like '* ROOT_ALIAS *' })
$apiLines = @($matches | Where-Object { $_ -like '* API *' })
$running = $null -ne (Get-Process -Name GoW -ErrorAction SilentlyContinue)

$header = @(
    'Completionist Map v0.10.4 Raven HUD instance runtime capture',
    ('Captured UTC: ' + [DateTime]::UtcNow.ToString('o')),
    ('Game process running while captured: ' + $running),
    ('Probe read-only: ' + [string]$m.read_only),
    ('mainhud pre-probe SHA256: ' + [string]$m.mainhud_before),
    ('mainhud probe SHA256: ' + [string]$m.mainhud_after),
    ('Total probe log lines: ' + $matches.Count),
    ('API lines: ' + $apiLines.Count),
    ('Root lines: ' + $rootLines.Count),
    ('Scan starts: ' + $scanLines.Count),
    ('Tracked=true lines: ' + $trackedLines.Count),
    ('HUD candidate hits: ' + $hitLines.Count),
    '',
    'INTERPRETATION GATE',
    'A useful positive result is one or more HIT lines that appear after tracked=true and identify a specific compass/HUD GameObject instance or child. No hit is also valid evidence and means name-based live lookup is insufficient.',
    'This capture does not authorise a global goboatdock resource/material swap. DockPoint.IconName is shared with real docks.',
    '',
    'RELEVANT LOADER LOG'
)

New-Item -ItemType Directory -Force -Path (Split-Path $report -Parent) | Out-Null
[IO.File]::WriteAllLines($report, @($header + $matches), $utf8)
Write-Host "Saved: $report"
Write-Host "Probe lines: $($matches.Count); hits: $($hitLines.Count); tracked=true lines: $($trackedLines.Count)"

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for HUD runtime report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed for HUD runtime report.' }

    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven HUD instance runtime' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for HUD runtime report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) {
            Write-Warning 'HUD runtime report was committed locally but push failed.'
        }
    }
    else {
        Write-Host 'HUD runtime report is unchanged; nothing to commit.'
    }
}
finally {
    Pop-Location
}

Write-Host 'No God of War files were modified by the collector.'
