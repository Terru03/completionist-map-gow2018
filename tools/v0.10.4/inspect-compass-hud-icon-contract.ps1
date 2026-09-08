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
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War completely before the read-only compass HUD contract scan.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
$script = Join-Path $PSScriptRoot 'inspect-compass-hud-icon-contract.py'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Missing script: $script" }

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v104-compass-hud-icon-contract.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

Write-Host 'Syntax-checking compass HUD icon contract inspector...'
& $python.Source -m py_compile $script
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed.' }

Write-Host 'Inspecting stock CompassIconClass IconName resources and native icon creation read-only...'
& $python.Source $script --game-root $GameRoot --output $out
if ($LASTEXITCODE -ne 0) { throw 'Compass HUD icon contract scan failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw 'Compass HUD icon contract report missing.' }

$report = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ([string]$report.result -ne 'READ_ONLY_COMPASS_HUD_ICON_CONTRACT' -or
    $report.game_files_written -ne $false -or
    $report.save_state_written -ne $false -or
    $report.progression_state_written -ne $false -or
    $report.marker_state_written -ne $false -or
    [string]$report.conclusion -ne 'HUD_ICONNAME_RESOURCE_CONTRACT_REQUIRES_SEPARATE_PROOF') {
    throw 'Compass HUD icon contract report failed safety/result validation.'
}

Write-Host ''
Write-Host 'Compass HUD icon contract scan complete.'
Write-Host "- stock classes: $($report.stock_compass_classes.Count)"
Write-Host "- Dock IconName WAD matches: $($report.dock_icon.matches.Count)"
Write-Host "- Raven hash WAD matches: $($report.raven_map_resource_hash.matches.Count)"
if ($null -ne $report.dock_vs_raven_payload) {
    Write-Host "- Dock/Raven final payload differences: $($report.dock_vs_raven_payload.difference_count)"
    Write-Host "- Dock prototype: $($report.dock_vs_raven_payload.dock_prototype_id_at_0x0C)"
    Write-Host "- Raven prototype: $($report.dock_vs_raven_payload.raven_prototype_id_at_0x0C)"
}
Write-Host "- native show function: $($report.native_show_icon_creation.function.begin)-$($report.native_show_icon_creation.function.end)"
Write-Host "- Capstone available: $($report.native_show_icon_creation.capstone.available)"
Write-Host "- conclusion: $($report.conclusion)"
Write-Host "- report: $out"
Write-Host '- game files written: false'

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive compass HUD icon contract scan' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Report committed and pushed to $Remote/$branch."
    }
} finally {
    Pop-Location
}
