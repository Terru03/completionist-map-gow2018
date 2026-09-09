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
    throw 'Close God of War completely before the Raven compass HUD registration audit.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
$audit = Join-Path $PSScriptRoot 'audit-raven-compass-hud-live-resolution.py'
if (-not (Test-Path -LiteralPath $audit -PathType Leaf)) { throw "Missing audit: $audit" }

$outRel = 'archive/field-logs/completionist-v104-raven-compass-hud-live-resolution.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

& $python.Source -m py_compile $audit
if ($LASTEXITCODE -ne 0) { throw 'Raven compass HUD audit syntax check failed.' }

& $python.Source $audit --game-root $GameRoot --output $out
if ($LASTEXITCODE -ne 0) { throw 'Raven compass HUD live-resolution audit failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw 'Raven compass HUD audit report was not created.' }

$proof = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
$allowed = @(
    'HUD_RESOURCE_NOT_PHYSICALLY_DEFINED',
    'HUD_RESOURCE_PHYSICAL_BUT_GOPool_UNREGISTERED',
    'HUD_RESOURCE_PHYSICAL_AND_GOPool_REGISTERED_DEEPER_AUDIT_REQUIRED'
)
if ([string]$proof.result -notin $allowed) { throw "Unexpected audit result: $($proof.result)" }
if ($proof.game_files_written -ne $false -or $proof.save_progression_marker_state_written -ne $false) {
    throw 'Audit safety invariant failed.'
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for HUD audit report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed for HUD audit report.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'HUD audit report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive Raven compass HUD live-resolution audit' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for HUD audit report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for HUD audit report.' }
        Write-Host "Pushed HUD audit report to $Remote/$branch"
    }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host 'RAVEN_COMPASS_HUD_LIVE_RESOLUTION_AUDIT_COMPLETE'
Write-Host ("  result: {0}" -f [string]$proof.result)
Write-Host ("  report: {0}" -f $out)
Write-Host '  game files written: false'
