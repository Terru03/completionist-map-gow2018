param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$candidateWad = Join-Path $repoRoot 'build\v0.10.4-nornir-mg-isolation\offline\r_ui.wad'
$archivedAudit = Join-Path $repoRoot 'archive\field-logs\completionist-v104-nornir-mg-isolated-candidate-audit.json'
$report = Join-Path $repoRoot 'build\v0.10.4-nornir-hidden-identity\offline\nornir-modelgroup-hidden-identity-audit.json'
$auditor = Join-Path $PSScriptRoot 'audit-nornir-modelgroup-hidden-identity.py'

Push-Location $repoRoot
try {
    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not determine current Git branch.' }
    if ($branch -ne 'codex/v104-raven-production') {
        throw "Wrong branch '$branch'. Expected codex/v104-raven-production."
    }

    if (-not (Test-Path -LiteralPath $candidateWad -PathType Leaf)) {
        throw "Missing isolated Candidate 2 WAD: $candidateWad`nDo not rebuild or install anything manually. Re-run the existing offline MG-isolation gate first if this build artifact was cleaned."
    }
    if (-not (Test-Path -LiteralPath $archivedAudit -PathType Leaf)) {
        throw "Missing archived isolation proof: $archivedAudit"
    }
    if (-not (Test-Path -LiteralPath $auditor -PathType Leaf)) {
        throw "Missing auditor: $auditor"
    }

    $reportDir = Split-Path -Parent $report
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

    Write-Host 'Running read-only Nornir model-group hidden-identity forensic audit...'
    Write-Host '  No God of War launch is required.'
    Write-Host '  No game, save, progression or marker-state files will be written.'
    Write-Host ''

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        & $py.Source -3 $auditor --candidate-wad $candidateWad --archived-audit $archivedAudit --report $report | Out-Host
    }
    else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $python) { throw 'Python was not found on PATH.' }
        & $python.Source $auditor --candidate-wad $candidateWad --archived-audit $archivedAudit --report $report | Out-Host
    }
    if ($LASTEXITCODE -ne 0) { throw "Hidden-identity auditor exited with code $LASTEXITCODE." }

    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) { throw 'Auditor did not create its JSON report.' }
    $proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json

    if ($proof.result -ne 'NORNIR_HIDDEN_IDENTITY_COLLISION_CONFIRMED') {
        throw "Unexpected audit result: $($proof.result)"
    }
    if (-not [bool]$proof.proofs.top_level_mg_names_and_ids_are_distinct) {
        throw 'Expected the Candidate 2 top-level MG records to be distinct.'
    }
    if (-not [bool]$proof.proofs.dedicated_map_mg_payload_is_byte_identical_to_stock_donor) {
        throw 'Map MG payload no longer matches the archived Candidate 2 failure condition.'
    }
    if (-not [bool]$proof.proofs.dedicated_hud_mg_payload_is_byte_identical_to_stock_donor) {
        throw 'HUD MG payload no longer matches the archived Candidate 2 failure condition.'
    }
    if ([bool]$proof.proofs.candidate2_runtime_install_allowed) {
        throw 'Safety invariant violated: Candidate 2 must remain blocked from runtime installation.'
    }
    if ([bool]$proof.safety.game_files_written) {
        throw 'Safety invariant violated: audit claims it wrote game files.'
    }

    Write-Host ''
    Write-Host 'NORNIR_HIDDEN_IDENTITY_COLLISION_CONFIRMED'
    Write-Host '  Candidate 2 retired: true'
    Write-Host '  top-level MG names/IDs distinct: true'
    Write-Host '  map MG physical payload still exact stock clone: true'
    Write-Host '  HUD MG physical payload still exact stock clone: true'
    Write-Host '  Candidate 2 runtime install allowed: false'
    Write-Host '  game files written: false'
    Write-Host '  next: construct a physically independent Nornir MG using Raven as structural reference; no runtime install yet'
    Write-Host "  report: $report"
}
finally {
    Pop-Location
}
