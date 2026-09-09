param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedBranch = 'codex/v104-raven-production'
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not determine current Git branch.' }
if ($branch -ne $expectedBranch) {
    throw "Expected branch '$expectedBranch', got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before running the Nornir resource-topology gate.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }

$verify = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$inspect = Join-Path $PSScriptRoot 'inspect-nornir-resource-topology.py'
foreach ($required in @($verify, $inspect)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing required tool: $required"
    }
}

Write-Host 'Re-verifying frozen Raven production state before Nornir resource planning...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed.' }

$nativeReport = Join-Path $repo 'build\v0.10.4-nornir-native-candidate\offline\nornir-native-data.json'
if (-not (Test-Path -LiteralPath $nativeReport -PathType Leaf)) {
    throw "Run the successful Nornir native-data offline gate first; report missing: $nativeReport"
}
$native = Get-Content -LiteralPath $nativeReport -Raw | ConvertFrom-Json
if ($native.result -ne 'OFFLINE_NORNIR_NATIVE_DATA_BUILT') {
    throw "Unexpected Nornir native-data report result: $($native.result)"
}
if ($native.generated_files.'mapmaster.dcb'.sha256 -ne 'dc51308e22807b3404ea951ae52f7daf28e8dbb442b09e59bfa98b4d243fc8fa') {
    throw 'Offline Nornir mapmaster candidate hash changed.'
}
if ($native.generated_files.'mapcoords.dcb'.sha256 -ne 'b870adccf66baf0d71dd1c0774d12e5ca503415da1e9270f82d0b77c0f11cd7f') {
    throw 'Offline Nornir mapcoords candidate hash changed.'
}
if ($native.generated_files.'compassgraph.dcb'.sha256 -ne '8477f6332436959ce06b0c7e84a4871a7ff947421f9e858589e360e2e7c0d45e') {
    throw 'Offline Nornir compassgraph candidate hash changed.'
}

$out = Join-Path $repo 'build\v0.10.4-nornir-resource-topology\nornir-resource-topology.json'
Remove-Item -LiteralPath $out -Force -ErrorAction SilentlyContinue

& $python.Source -m py_compile $inspect
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed for Nornir resource-topology inspector.' }

Write-Host 'Inspecting the exact Raven map/HUD/in-world donors and collision-free Nornir namespace...'
& $python.Source $inspect --game-root $GameRoot --repo-root $repo --output $out
if ($LASTEXITCODE -ne 0) { throw 'Nornir resource-topology inspection failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) {
    throw 'Nornir resource-topology report was not produced.'
}

$report = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ($report.result -ne 'NORNIR_RESOURCE_TOPOLOGY_VERIFIED' -or -not $report.ready_for_nornir_resource_builder) {
    throw 'Nornir resource-topology report did not pass the builder gate.'
}
if ($report.safety.game_files_written -or
    $report.safety.runtime_install_performed -or
    $report.safety.save_state_written -or
    $report.safety.progression_state_written -or
    $report.safety.marker_state_written -or
    $report.safety.raven_production_files_changed -or
    $report.safety.stock_DockPoint_resources_modified) {
    throw 'Safety contract failed in Nornir resource-topology report.'
}

Write-Host 'NORNIR_RESOURCE_TOPOLOGY_GATE_PASSED'
Write-Host "map GO:       $($report.planned_nornir.names.map_go) = $($report.planned_nornir.hashes.map_go)"
Write-Host "HUD GO:       $($report.planned_nornir.names.hud_go) = $($report.planned_nornir.hashes.hud_go)"
Write-Host "class:        $($report.planned_nornir.names.class) = $($report.planned_nornir.hashes.class)"
Write-Host "in-world:     $($report.planned_nornir.names.inworld) = $($report.planned_nornir.hashes.inworld)"
Write-Host "diffuse:      $($report.planned_nornir.names.diffuse)"
Write-Host "emissive:     $($report.planned_nornir.names.emissive)"
Write-Host "GOPool:       $($report.planned_nornir.gopool_plan.current_rows) -> $($report.planned_nornir.gopool_plan.resulting_rows) rows"
Write-Host 'Raven donor topology verified: true'
Write-Host 'Nornir WAD/export/GOPool collisions: 0'
Write-Host 'real Nornir art sources verified: true'
Write-Host 'Raven production files changed: false'
Write-Host 'game files written: false'
Write-Host 'runtime install performed: false'
Write-Host "report: $out"
Write-Host 'No Nornir resource has been authored into the game. This is the final read-only gate before the real art/resource candidate builder.'
