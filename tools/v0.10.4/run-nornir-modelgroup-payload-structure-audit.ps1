param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$candidateWad = Join-Path $repoRoot 'build\v0.10.4-nornir-mg-isolation\offline\r_ui.wad'
$hiddenReport = Join-Path $repoRoot 'build\v0.10.4-nornir-hidden-identity\offline\nornir-modelgroup-hidden-identity-audit.json'
$report = Join-Path $repoRoot 'build\v0.10.4-nornir-mg-payload-structure\offline\nornir-modelgroup-payload-structure-audit.json'
$auditor = Join-Path $PSScriptRoot 'audit-nornir-modelgroup-payload-structure.py'

Push-Location $repoRoot
try {
    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not determine current Git branch.' }
    if ($branch -ne 'codex/v104-raven-production') {
        throw "Wrong branch '$branch'. Expected codex/v104-raven-production."
    }

    $gow = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }
    if ($gow) {
        throw 'God of War is running. Close it before the offline forensic audit.'
    }

    if (-not (Test-Path -LiteralPath $candidateWad -PathType Leaf)) {
        throw "Missing retired Candidate 2 WAD: $candidateWad`nRe-run the existing OFFLINE MG-isolation gate only. Do not install Candidate 2."
    }
    if (-not (Test-Path -LiteralPath $hiddenReport -PathType Leaf)) {
        throw "Missing hidden-identity prerequisite report: $hiddenReport`nRun .\tools\v0.10.4\run-nornir-modelgroup-hidden-identity-audit.ps1 first."
    }
    if (-not (Test-Path -LiteralPath $auditor -PathType Leaf)) {
        throw "Missing auditor: $auditor"
    }

    $hidden = Get-Content -LiteralPath $hiddenReport -Raw | ConvertFrom-Json
    if ($hidden.result -ne 'NORNIR_HIDDEN_IDENTITY_COLLISION_CONFIRMED') {
        throw "Hidden-identity prerequisite did not pass: $($hidden.result)"
    }
    if ([bool]$hidden.proofs.candidate2_runtime_install_allowed) {
        throw 'Safety invariant violated: Candidate 2 is not retired in the prerequisite report.'
    }
    if ([bool]$hidden.proofs.specific_internal_identity_field_proven) {
        throw 'Prerequisite unexpectedly claims a decoded internal identity field. Stop and review.'
    }

    $reportDir = Split-Path -Parent $report
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

    Write-Host 'Running read-only Nornir MG payload-structure audit...'
    Write-Host '  Candidate 2 remains retired.'
    Write-Host '  No Candidate 3 will be constructed.'
    Write-Host '  No God of War launch is required.'
    Write-Host '  No game, save, progression or marker-state files will be written.'
    Write-Host ''

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        & $py.Source -3 $auditor --candidate-wad $candidateWad --hidden-audit $hiddenReport --report $report | Out-Host
    }
    else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $python) { throw 'Python was not found on PATH.' }
        & $python.Source $auditor --candidate-wad $candidateWad --hidden-audit $hiddenReport --report $report | Out-Host
    }
    if ($LASTEXITCODE -ne 0) {
        throw "MG payload-structure auditor exited with code $LASTEXITCODE."
    }

    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        throw 'Auditor did not create its JSON report.'
    }
    $proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json

    if ($proof.result -ne 'NORNIR_MODEL_GROUP_PAYLOAD_STRUCTURE_AUDIT_PASSED') {
        throw "Unexpected audit result: $($proof.result)"
    }
    if (-not [bool]$proof.proofs.candidate2_retired) {
        throw 'Safety invariant violated: Candidate 2 is not marked retired.'
    }
    if (-not [bool]$proof.proofs.candidate2_map_payload_still_exact_stock_clone) {
        throw 'Map Candidate 2 clone condition changed.'
    }
    if (-not [bool]$proof.proofs.candidate2_hud_payload_still_exact_stock_clone) {
        throw 'HUD Candidate 2 clone condition changed.'
    }
    if ([bool]$proof.proofs.specific_internal_identity_field_proven) {
        throw 'Audit must not infer an opaque identity field from correlation alone.'
    }
    if ([bool]$proof.proofs.candidate3_constructed) {
        throw 'Safety invariant violated: this audit must not construct Candidate 3.'
    }
    if ([bool]$proof.proofs.runtime_install_allowed) {
        throw 'Safety invariant violated: runtime install must remain blocked.'
    }
    if ([bool]$proof.safety.game_files_written) {
        throw 'Safety invariant violated: audit claims it wrote game files.'
    }

    Write-Host ''
    Write-Host 'NORNIR_MODEL_GROUP_PAYLOAD_STRUCTURE_AUDIT_PASSED'
    Write-Host '  Candidate 2 retired: true'
    Write-Host "  native exact-payload equivalence classes: $($proof.model_group_inventory.native_only_exact_payload_equivalence_class_count)"
    Write-Host "  map native same-size payloads incl donor: $($proof.pairs.map.native_same_size_payload_count_including_donor)"
    Write-Host "  map native exact payload peers excl donor: $($proof.pairs.map.native_exact_payload_peer_count_excluding_donor)"
    Write-Host "  HUD native same-size payloads incl donor: $($proof.pairs.hud.native_same_size_payload_count_including_donor)"
    Write-Host "  HUD native exact payload peers excl donor: $($proof.pairs.hud.native_exact_payload_peer_count_excluding_donor)"
    Write-Host '  specific hidden identity field proven: false'
    Write-Host '  Candidate 3 constructed: false'
    Write-Host '  runtime install allowed: false'
    Write-Host '  game files written: false'
    Write-Host '  next: inspect native peer differentials before defining any Candidate 3 byte transform'
    Write-Host "  report: $report"
}
finally {
    Pop-Location
}
