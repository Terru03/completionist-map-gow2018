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
    throw 'Close God of War before the native ShowMarker validation scan.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$scanner = Join-Path $PSScriptRoot 'inspect-compass-showmarker-native-validation.py'
$outRel = 'archive/field-logs/completionist-v104-compass-showmarker-native-validation.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) { throw "Missing scanner: $scanner" }
if (-not (Test-Path -LiteralPath $game -PathType Container)) { throw "Missing game root: $game" }
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$preStaged = @(& git -C $repo diff --cached --name-only)
if ($preStaged.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace(($preStaged -join ''))) {
    throw "Git index already has staged changes. Commit/unstage them before running this archive helper.`n$($preStaged -join "`n")"
}

Write-Host 'Syntax-checking native ShowMarker validation inspector...'
& $python.Source -m py_compile $scanner
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed.' }

Write-Host 'Inspecting pinned GoW.exe ShowMarker validator read-only...'
& $python.Source $scanner --game-root $game --output $out
if ($LASTEXITCODE -ne 0) { throw 'Native ShowMarker validation scan failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw "Report was not produced: $out" }

$r = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ([string]$r.result -ne 'READ_ONLY_COMPASS_SHOWMARKER_NATIVE_VALIDATION') {
    throw "Unexpected result: $($r.result)"
}
if ($r.game_files_written -ne $false -or $r.save_progression_marker_state_written -ne $false) {
    throw 'Read-only safety flags failed.'
}
if ([string]$r.source_sha256 -ne 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452') {
    throw 'Pinned GoW.exe hash validation failed.'
}
if ([string]$r.prior_static_anchors.LuaCompass_ShowMarker_rva -ne '0x94FF80' -or
    [string]$r.prior_static_anchors.CompassIconClass_0x11E_check_site_rva -ne '0x95009E') {
    throw 'Prior native ShowMarker anchors were not preserved.'
}

$errRefs = @($r.heuristic_error_string_refs).Count
$typeImms = @($r.raw_0x11e_u32_occurrences_inside_showmarker).Count
if ($r.capstone.available -eq $true) {
    $errRefs = @($r.capstone.error_string_refs).Count
    $typeImms = @($r.capstone.type_0x11e_immediates).Count
}

Write-Host ''
Write-Host 'Native ShowMarker validation scan complete.'
Write-Host ("- conclusion: {0}" -f [string]$r.conclusion)
Write-Host ("- ShowMarker function: {0}-{1}" -f [string]$r.showmarker_runtime_function.begin_rva, [string]$r.showmarker_runtime_function.end_rva)
Write-Host ("- invalid-type string RVA: {0}" -f [string]$r.invalid_type_string.rva)
Write-Host ("- invalid-type refs in ShowMarker: {0}" -f $errRefs)
Write-Host ("- type-0x11E immediates in ShowMarker: {0}" -f $typeImms)
Write-Host ("- capstone available: {0}" -f [bool]$r.capstone.available)
if ($r.capstone.available -eq $true) {
    Write-Host ("- calls near 0x11E check: {0}" -f @($r.capstone.near_type_check_calls).Count)
}
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

& git -C $repo commit -m 'Archive native ShowMarker validation scan' -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
& git -C $repo push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
Write-Host "Report committed and pushed to $Remote/$branch."
