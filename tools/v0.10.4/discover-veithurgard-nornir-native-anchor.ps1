param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [int]$Limit = 10
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/v104-raven-production'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$VerifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$Discover = Join-Path $PSScriptRoot 'discover-native-route-anchor.py'
$Observed = Join-Path $RepoRoot 'data\observed\veithurgard-nornir-breakable-v0.8.json'
$RavenManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-production\active.json'
$StateDir = Join-Path $RepoRoot 'build\v0.10.4-nornir-native-anchor'
$Report = Join-Path $StateDir 'veithurgard-nornir-chest.json'

$branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
    throw "Expected Git branch '$ExpectedBranch', found '$branch'."
}

$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
})
if ($running.Count -gt 0) {
    throw 'God of War is running. Close it before native-route discovery.'
}

if ($Limit -lt 3 -or $Limit -gt 50) {
    throw 'Limit must be between 3 and 50.'
}

foreach ($required in @($VerifyRaven, $Discover, $Observed, $RavenManifest)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing required file: $required"
    }
}

$baseline = Get-Content -LiteralPath $RavenManifest -Raw | ConvertFrom-Json
if ([string]$baseline.kind -ne 'completionist-v104-raven-production-baseline' -or
    $baseline.schema -ne 1 -or
    [string]$baseline.status -ne 'adopted' -or
    $baseline.runtime_invariants.crash_free -ne $true -or
    $baseline.runtime_invariants.native_pathfinding -ne $true -or
    $baseline.runtime_invariants.single_active_target -ne $true) {
    throw 'Adopted Raven production manifest does not satisfy the frozen production contract.'
}

Write-Host 'Re-verifying frozen Raven production state before Nornir research...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $VerifyRaven -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Raven production verification failed; refusing Nornir route discovery.'
}

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python 3 is required.' }

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

Write-Host ''
Write-Host 'Discovering stock native route anchors around the observed Veithurgard Nornir chest...'
& $python.Source $Discover `
    --game-root $GameRoot `
    --observed $Observed `
    --selector chest `
    --limit $Limit `
    --output $Report
if ($LASTEXITCODE -ne 0) {
    throw 'Nornir native-route anchor discovery failed.'
}
if (-not (Test-Path -LiteralPath $Report -PathType Leaf)) {
    throw 'Discovery did not create its report.'
}

$proof = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'NATIVE_ROUTE_ANCHOR_DISCOVERY_READ_ONLY' -or
    $proof.game_files_written -ne $false -or
    $proof.saves_progression_marker_state_written -ne $false -or
    [string]$proof.selector -ne 'chest') {
    throw 'Nornir discovery report did not satisfy the read-only contract.'
}

if (@($proof.nearest_stock_map_coordinates).Count -lt 1 -or @($proof.nearest_stock_helpers).Count -lt 1) {
    throw 'Discovery returned no stock route candidates.'
}

Write-Host ''
Write-Host 'NORNIR_NATIVE_ANCHOR_DISCOVERY_PASSED'
Write-Host "  target: $($proof.target.label)"
Write-Host ("  world:  {0}, {1}, {2}" -f $proof.target.world_position[0], $proof.target.world_position[1], $proof.target.world_position[2])
Write-Host '  nearest stock map-coordinate candidates:'
@($proof.nearest_stock_map_coordinates) | Select-Object -First 5 | ForEach-Object {
    $neighbours = @($_.edge_neighbours) -join ','
    if ([string]::IsNullOrWhiteSpace($neighbours)) { $neighbours = '-' }
    Write-Host ("    {0}  {1}m  wad={2}  neighbours={3}" -f $_.id, $_.straight_line_metres_for_research, $_.wad, $neighbours)
}
Write-Host '  nearest stock helper candidates:'
@($proof.nearest_stock_helpers) | Select-Object -First 5 | ForEach-Object {
    $neighbours = @($_.edge_neighbours) -join ','
    if ([string]::IsNullOrWhiteSpace($neighbours)) { $neighbours = '-' }
    Write-Host ("    {0}  {1}m  wad={2}  neighbours={3}" -f $_.id, $_.straight_line_metres_for_research, $_.wad, $neighbours)
}
Write-Host '  Raven production files changed: false'
Write-Host '  game files written: false'
Write-Host '  saves/progression/marker state written: false'
Write-Host "  report: $Report"
Write-Host ''
Write-Host 'No Nornir marker has been authored or installed yet. Review these candidates before choosing a native graph neighbour.'
