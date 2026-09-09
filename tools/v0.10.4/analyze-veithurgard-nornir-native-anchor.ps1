param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/v104-raven-production'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$VerifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$Analyze = Join-Path $PSScriptRoot 'analyze-native-route-anchor-topology.py'
$Discovery = Join-Path $RepoRoot 'build\v0.10.4-nornir-native-anchor\veithurgard-nornir-chest.json'
$StateDir = Join-Path $RepoRoot 'build\v0.10.4-nornir-native-anchor'
$Report = Join-Path $StateDir 'veithurgard-nornir-topology.json'

$branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
    throw "Expected Git branch '$ExpectedBranch', found '$branch'."
}

$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
})
if ($running.Count -gt 0) {
    throw 'God of War is running. Close it before native-route topology analysis.'
}

foreach ($required in @($VerifyRaven, $Analyze, $Discovery)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing required file: $required"
    }
}

Write-Host 'Re-verifying frozen Raven production state before Nornir topology analysis...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $VerifyRaven -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Raven production verification failed; refusing Nornir topology analysis.'
}

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python 3 is required.' }

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

Write-Host ''
Write-Host 'Comparing Veithurgard Nornir helper candidates with the runtime-proven Raven native-route anchor...'
& $python.Source $Analyze `
    --game-root $GameRoot `
    --discovery $Discovery `
    --output $Report
if ($LASTEXITCODE -ne 0) {
    throw 'Nornir native-route topology analysis failed.'
}
if (-not (Test-Path -LiteralPath $Report -PathType Leaf)) {
    throw 'Topology analyzer did not create its report.'
}

$proof = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'NATIVE_ROUTE_ANCHOR_TOPOLOGY_READ_ONLY' -or
    $proof.game_files_written -ne $false -or
    $proof.saves_progression_marker_state_written -ne $false -or
    $proof.runtime_proven_raven_reference.edge_verified -ne $true) {
    throw 'Topology report did not satisfy the read-only Raven-reference contract.'
}

Write-Host ''
Write-Host 'NORNIR_NATIVE_ANCHOR_TOPOLOGY_PASSED'
Write-Host ("  Raven anchor: {0} kind={1} type={2} degree={3}" -f `
    $proof.runtime_proven_raven_reference.anchor_id, `
    $proof.runtime_proven_raven_reference.anchor_kind, `
    $proof.runtime_proven_raven_reference.anchor_helper_type, `
    $proof.runtime_proven_raven_reference.anchor_degree)
Write-Host '  ranked Nornir helper candidates:'
@($proof.candidate_ranking) | Select-Object -First 10 | ForEach-Object {
    Write-Host ("    {0}  {1}m  type={2}  sameRavenType={3}  sameComponent={4}  degree={5}  stepsToStockCoord={6}" -f `
        $_.id, $_.distance_to_target_m, $_.helper_type, $_.same_helper_type_as_raven_anchor, `
        $_.same_graph_component_as_raven_anchor, $_.degree, $_.nearest_stock_map_coordinate_graph_steps)
}
Write-Host "  provisional same-type nearest: $($proof.provisional_same-type_nearest_candidate)"
Write-Host '  Raven production files changed: false'
Write-Host '  game files written: false'
Write-Host '  saves/progression/marker state written: false'
Write-Host "  report: $Report"
Write-Host ''
Write-Host 'No Nornir marker has been authored or installed. This report is the final topology gate before selecting the graph neighbour.'
