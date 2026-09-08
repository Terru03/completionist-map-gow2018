param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$NoPublish
)

$ErrorActionPreference = 'Stop'

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected branch codex/v104-raven-hud-research, got '$branch'."
}

$game = [IO.Path]::GetFullPath($GameRoot)
$source = Join-Path $game 'exec\dc\pc_le\wad_r_perm.dcb'
$builder = Join-Path $PSScriptRoot 'build-packed-raven-compass-class.py'
$buildDir = Join-Path $repo 'build\v0.10.4-packed-raven-compass-class\game-root\exec\dc\pc_le'
$output = Join-Path $buildDir 'wad_r_perm.dcb'
$report = Join-Path $repo 'archive\field-logs\completionist-v104-packed-raven-compass-class.json'
$expectedSource = 'EABB9E548202E2F710520A0FAB905952CEFC10FFB2B6B5540E773D64EB1D8039'

function Hash-File([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Missing source DCB: $source"
}
if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) {
    throw "Missing builder: $builder"
}

$before = Hash-File $source
if ($before -ne $expectedSource) {
    throw "wad_r_perm.dcb is not the researched stock file. Expected $expectedSource, got $before"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    throw 'Python 3.9+ is required.'
}

Write-Host 'Syntax-checking packed Raven class builder...'
& $python.Source -m py_compile $builder
if ($LASTEXITCODE -ne 0) {
    throw 'Python syntax check failed.'
}

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $report -Parent) | Out-Null

Write-Host 'Building packed CompletionistRaven CompassIconClass candidate OFFLINE...'
& $python.Source $builder --game-root $game --output $output --report $report
if ($LASTEXITCODE -ne 0) {
    throw 'Packed Raven CompassIconClass build failed.'
}

$after = Hash-File $source
if ($after -ne $before) {
    throw 'Source wad_r_perm.dcb changed during offline build.'
}

if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
    throw "Candidate DCB was not produced: $output"
}
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw "Build report was not produced: $report"
}

$r = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ([string]$r.result -ne 'OFFLINE_PACKED_COMPLETIONIST_RAVEN_COMPASS_CLASS_BUILT') {
    throw "Unexpected result: $($r.result)"
}
if ($r.game_files_written -ne $false -or $r.installed -ne $false) {
    throw 'Offline safety flags failed.'
}
if ([string]$r.new_class.name -ne 'CompletionistRaven' -or
    [string]$r.new_class.uid -ne '5DC46967D3095F7E' -or
    [string]$r.new_class.root -ne '0x4E2C50' -or
    $r.new_class.record_bytes_equal_dockpoint -ne $true) {
    throw 'CompletionistRaven class identity/root validation failed.'
}
if ($r.validation.candidate_exact_0x20_stride -ne $true -or
    [string]$r.validation.COMPASS_GLOBALS_shifted_to -ne '0x4E2C70' -or
    $r.validation.all_stock_exports_preserved -ne $true -or
    $r.validation.all_stock_relocations_preserved_semantically -ne $true) {
    throw 'Packed-block structural validation failed.'
}
foreach ($kind in @('11','14','35')) {
    if ($r.unchanged_metadata_chunk_payloads.$kind -ne $true) {
        throw "Metadata chunk $kind changed unexpectedly."
    }
}
if ($r.safety.game_directory_written -ne $false -or
    $r.safety.save_state_written -ne $false -or
    $r.safety.progression_state_written -ne $false -or
    $r.safety.map_marker_state_written -ne $false -or
    $r.safety.map_raven_artwork_touched -ne $false -or
    $r.safety.real_dock_visuals_touched -ne $false) {
    throw 'Safety validation failed.'
}

Write-Host ''
Write-Host 'Packed Raven class offline build passed.'
Write-Host ("- candidate: {0}" -f $output)
Write-Host ("- report:    {0}" -f $report)
Write-Host ("- source SHA256 unchanged: {0}" -f $after)
Write-Host ("- candidate SHA256: {0}" -f (Hash-File $output))
Write-Host '- game files written: false'
Write-Host '- saves/progression/marker state touched: false'

if ($NoPublish) {
    Write-Host 'Report publishing skipped (-NoPublish).'
    return
}

& git -C $repo add -- 'archive/field-logs/completionist-v104-packed-raven-compass-class.json'
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }

$staged = (& git -C $repo diff --cached --name-only).Trim()
if (-not $staged) {
    Write-Host 'No report changes to commit.'
    return
}

& git -C $repo commit -m 'Archive packed Raven compass class build'
if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }

& git -C $repo push origin $branch
if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }

Write-Host 'Report committed and pushed.'
