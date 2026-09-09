param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$candidateWad = Join-Path $repoRoot 'build\v0.10.4-nornir-mg-isolation\offline\r_ui.wad'
$structureReport = Join-Path $repoRoot 'build\v0.10.4-nornir-mg-payload-structure\offline\nornir-modelgroup-payload-structure-audit.json'
$report = Join-Path $repoRoot 'build\v0.10.4-nornir-mg-peer-differential\offline\nornir-modelgroup-peer-differential-audit.json'
$auditor = Join-Path $PSScriptRoot 'audit-nornir-modelgroup-peer-differentials.py'

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
        throw "Missing retired Candidate 2 WAD: $candidateWad`nRe-run the existing offline MG-isolation gate only. Do not install Candidate 2."
    }
    if (-not (Test-Path -LiteralPath $structureReport -PathType Leaf)) {
        throw "Missing payload-structure prerequisite report: $structureReport`nRun .\tools\v0.10.4\run-nornir-modelgroup-payload-structure-audit.ps1 first."
    }
    if (-not (Test-Path -LiteralPath $auditor -PathType Leaf)) {
        throw "Missing auditor: $auditor"
    }

    $prior = Get-Content -LiteralPath $structureReport -Raw | ConvertFrom-Json
    if ($prior.result -ne 'NORNIR_MODEL_GROUP_PAYLOAD_STRUCTURE_AUDIT_PASSED') {
        throw "Payload-structure prerequisite did not pass: $($prior.result)"
    }
    if (-not [bool]$prior.proofs.candidate2_retired) {
        throw 'Safety invariant violated: Candidate 2 is not retired in the prerequisite report.'
    }
    if ([bool]$prior.proofs.specific_internal_identity_field_proven) {
        throw 'Prerequisite unexpectedly claims a decoded hidden identity field. Stop and review.'
    }
    if ([bool]$prior.proofs.candidate3_constructed) {
        throw 'Prerequisite unexpectedly claims Candidate 3 was constructed.'
    }
    if ([bool]$prior.proofs.runtime_install_allowed) {
        throw 'Prerequisite unexpectedly allows a runtime install.'
    }

    $reportDir = Split-Path -Parent $report
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

    Write-Host 'Running read-only Nornir MG native-peer differential audit...'
    Write-Host '  Candidate 2 remains retired.'
    Write-Host '  No Candidate 3 will be constructed.'
    Write-Host '  No God of War launch is required.'
    Write-Host '  No game, save, progression or marker-state files will be written.'
    Write-Host ''

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        & $py.Source -3 $auditor --candidate-wad $candidateWad --structure-report $structureReport --report $report | Out-Host
    }
    else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $python) { throw 'Python was not found on PATH.' }
        & $python.Source $auditor --candidate-wad $candidateWad --structure-report $structureReport --report $report | Out-Host
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Native-peer differential auditor exited with code $LASTEXITCODE."
    }

    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        throw 'Auditor did not create its JSON report.'
    }
    $proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json

    if ($proof.result -ne 'NORNIR_MODEL_GROUP_NATIVE_PEER_DIFFERENTIAL_AUDIT_PASSED') {
        throw "Unexpected audit result: $($proof.result)"
    }
    if (-not [bool]$proof.proofs.candidate2_retired) {
        throw 'Safety invariant violated: Candidate 2 retirement was lost.'
    }
    if (-not [bool]$proof.proofs.native_same_size_peer_differentials_measured) {
        throw 'Expected native same-size peer differentials to be measured.'
    }
    if (-not [bool]$proof.proofs.known_resource_id_overlap_measured) {
        throw 'Expected known resource-ID overlap evidence to be measured.'
    }
    if ([bool]$proof.proofs.specific_internal_identity_field_proven) {
        throw 'Audit must not infer an opaque identity field from differential correlation alone.'
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
    Write-Host 'NORNIR_MODEL_GROUP_NATIVE_PEER_DIFFERENTIAL_AUDIT_PASSED'
    Write-Host '  Candidate 2 retired: true'
    Write-Host "  map minimum native diff bytes: $($proof.pairs.map.minimum_native_diff_bytes)"
    Write-Host "  map closest cohort: $($proof.pairs.map.closest_cohort_members -join ', ')"
    Write-Host "  map closest common differential bytes: $($proof.pairs.map.closest_cohort_common_offsets.offset_count)"
    Write-Host "  HUD minimum native diff bytes: $($proof.pairs.hud.minimum_native_diff_bytes)"
    Write-Host "  HUD closest cohort: $($proof.pairs.hud.closest_cohort_members -join ', ')"
    Write-Host "  HUD closest common differential bytes: $($proof.pairs.hud.closest_cohort_common_offsets.offset_count)"
    Write-Host '  specific hidden identity field proven: false'
    Write-Host '  Candidate 3 constructed: false'
    Write-Host '  runtime install allowed: false'
    Write-Host '  game files written: false'
    Write-Host '  next: inspect whether the native differential runs resolve to known resource references or remain opaque before defining Candidate 3'
    Write-Host "  report: $report"
}
finally {
    Pop-Location
}
