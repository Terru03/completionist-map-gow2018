param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$candidateWad = Join-Path $repoRoot 'build\v0.10.4-nornir-mg-isolation\offline\r_ui.wad'
$peerReport = Join-Path $repoRoot 'build\v0.10.4-nornir-mg-peer-differential\offline\nornir-modelgroup-peer-differential-audit.json'
$report = Join-Path $repoRoot 'build\v0.10.4-nornir-mg-scalar-fields\offline\nornir-modelgroup-scalar-field-audit.json'
$auditor = Join-Path $PSScriptRoot 'audit-nornir-modelgroup-scalar-fields.py'

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
        throw 'God of War is running. Close it before the offline scalar-field audit.'
    }

    if (-not (Test-Path -LiteralPath $candidateWad -PathType Leaf)) {
        throw "Missing retired Candidate 2 WAD: $candidateWad`nRe-run the existing OFFLINE MG-isolation gate only. Do not install Candidate 2."
    }
    if (-not (Test-Path -LiteralPath $peerReport -PathType Leaf)) {
        throw "Missing native-peer differential prerequisite: $peerReport`nRun .\tools\v0.10.4\run-nornir-modelgroup-peer-differential-audit.ps1 first."
    }
    if (-not (Test-Path -LiteralPath $auditor -PathType Leaf)) {
        throw "Missing auditor: $auditor"
    }

    $prior = Get-Content -LiteralPath $peerReport -Raw | ConvertFrom-Json
    if ($prior.result -ne 'NORNIR_MODEL_GROUP_NATIVE_PEER_DIFFERENTIAL_AUDIT_PASSED') {
        throw "Native-peer differential prerequisite did not pass: $($prior.result)"
    }
    if (-not [bool]$prior.proofs.candidate2_retired) {
        throw 'Safety invariant violated: Candidate 2 is not marked retired.'
    }
    if ([bool]$prior.proofs.specific_internal_identity_field_proven) {
        throw 'Prerequisite unexpectedly claims a decoded hidden identity field. Stop and review.'
    }
    if ([bool]$prior.proofs.candidate3_constructed) {
        throw 'Safety invariant violated: Candidate 3 already exists unexpectedly.'
    }
    if ([bool]$prior.proofs.runtime_install_allowed) {
        throw 'Safety invariant violated: runtime gate is unexpectedly open.'
    }

    $reportDir = Split-Path -Parent $report
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

    Write-Host 'Running read-only Nornir MG scalar/word-field audit...'
    Write-Host '  Candidate 2 remains retired.'
    Write-Host '  Opaque native differential bytes will be decoded only as candidate scalar representations.'
    Write-Host '  No field semantics will be assumed.'
    Write-Host '  No Candidate 3 will be constructed.'
    Write-Host '  No God of War launch is required.'
    Write-Host '  No game, save, progression or marker-state files will be written.'
    Write-Host ''

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        & $py.Source -3 $auditor --candidate-wad $candidateWad --peer-report $peerReport --report $report | Out-Host
    }
    else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $python) { throw 'Python was not found on PATH.' }
        & $python.Source $auditor --candidate-wad $candidateWad --peer-report $peerReport --report $report | Out-Host
    }
    if ($LASTEXITCODE -ne 0) {
        throw "MG scalar-field auditor exited with code $LASTEXITCODE."
    }

    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        throw 'Auditor did not create its JSON report.'
    }
    $proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json

    if ($proof.result -ne 'NORNIR_MODEL_GROUP_SCALAR_FIELD_AUDIT_PASSED') {
        throw "Unexpected audit result: $($proof.result)"
    }
    if (-not [bool]$proof.proofs.candidate2_retired) {
        throw 'Safety invariant violated: Candidate 2 retirement proof missing.'
    }
    if ([bool]$proof.proofs.specific_internal_identity_field_proven) {
        throw 'Scalar audit must not promote numeric interpretations to field semantics.'
    }
    if ([bool]$proof.proofs.candidate3_constructed) {
        throw 'Safety invariant violated: scalar audit constructed Candidate 3.'
    }
    if ([bool]$proof.proofs.runtime_install_allowed) {
        throw 'Safety invariant violated: runtime install must remain blocked.'
    }
    if ([bool]$proof.safety.game_files_written) {
        throw 'Safety invariant violated: audit claims it wrote game files.'
    }

    Write-Host ''
    Write-Host 'NORNIR_MODEL_GROUP_SCALAR_FIELD_AUDIT_PASSED'
    Write-Host '  Candidate 2 retired: true'
    Write-Host "  map aligned words covering native differential: $($proof.pairs.map.aligned_word_count_covering_signature)"
    Write-Host "  map shared closest words differing from donor: $($proof.pairs.map.closest_cohort_shared_word_different_from_donor_count)"
    Write-Host "  HUD aligned words covering native differential: $($proof.pairs.hud.aligned_word_count_covering_signature)"
    Write-Host "  HUD shared closest words differing from donor: $($proof.pairs.hud.closest_cohort_shared_word_different_from_donor_count)"
    Write-Host '  specific hidden identity field proven: false'
    Write-Host '  Candidate 3 constructed: false'
    Write-Host '  runtime install allowed: false'
    Write-Host '  game files written: false'
    Write-Host '  next: review exact scalar-word patterns; only then decide whether a field family is coherent enough for deeper semantic tracing'
    Write-Host "  report: $report"
}
finally {
    Pop-Location
}
