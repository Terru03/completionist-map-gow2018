param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin',
    [switch]$NoPublish
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before the Compass type-validation source scan.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$scanner = Join-Path $PSScriptRoot 'inspect-compass-type-validation-source.py'
$outRel = 'archive/field-logs/completionist-v104-compass-type-validation-source.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) {
    throw "Missing scanner: $scanner"
}
if (-not (Test-Path -LiteralPath $game -PathType Container)) {
    throw "Missing game root: $game"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    throw 'Python 3.9+ is required.'
}

$preStaged = @(& git -C $repo diff --cached --name-only)
if ($preStaged.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace(($preStaged -join ''))) {
    throw "Git index already has staged changes. Commit/unstage them before running this archive helper.`n$($preStaged -join "`n")"
}

Write-Host 'Syntax-checking Compass type-validation scanner...'
& $python.Source -m py_compile $scanner
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed.' }

Write-Host 'Scanning recovered Lua/text sources and targeted GoW binaries read-only...'
& $python.Source $scanner --game-root $game --repo-root $repo --output $out
if ($LASTEXITCODE -ne 0) { throw 'Compass type-validation source scan failed.' }

if (-not (Test-Path -LiteralPath $out -PathType Leaf)) {
    throw "Report was not produced: $out"
}
$r = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ([string]$r.result -ne 'READ_ONLY_COMPASS_TYPE_VALIDATION_SCAN') {
    throw "Unexpected scan result: $($r.result)"
}
if ($r.game_files_written -ne $false -or $r.save_progression_marker_state_written -ne $false) {
    throw 'Read-only safety flags failed.'
}

Write-Host ''
Write-Host 'Compass type-validation scan complete.'
Write-Host ("- conclusion: {0}" -f [string]$r.conclusion)
Write-Host ("- text files scanned: {0}" -f [int]$r.scanned_text_files)
Write-Host ("- target binaries scanned: {0}" -f [int]$r.scanned_target_binaries)
Write-Host ("- exact invalid-type sources: {0}" -f (@($r.exact_error_sources).Count + @($r.binary_exact_error_sources).Count))
Write-Host ("- core.class sources: {0}" -f (@($r.core_class_sources).Count + @($r.binary_core_class_sources).Count))
Write-Host ("- registry candidates: {0}" -f @($r.registry_candidates).Count)
Write-Host ("- report: {0}" -f $out)
Write-Host '- game files written: false'

if ($NoPublish) {
    Write-Host 'Report publishing skipped (-NoPublish).'
    return
}

& git -C $repo add -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
& git -C $repo diff --cached --check -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

& git -C $repo diff --cached --quiet -- $outRel
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Report unchanged; nothing new to commit.'
    return
}

& git -C $repo commit -m 'Archive Compass type validation source scan' -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
& git -C $repo push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
Write-Host "Report committed and pushed to $Remote/$branch."
