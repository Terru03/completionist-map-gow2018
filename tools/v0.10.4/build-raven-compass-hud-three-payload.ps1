param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$builder = Join-Path $PSScriptRoot 'build-raven-compass-hud-three-payload-v2.py'
if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) {
    throw "Missing builder: $builder"
}

Write-Host 'Syntax-checking dependency-aware offline Raven compass HUD builder...'
$sourceCode = [IO.File]::ReadAllText($builder)
$sourceCode | & $python.Source -c 'import ast,sys; ast.parse(sys.stdin.read())'
if ($LASTEXITCODE -ne 0) { throw 'Offline Raven compass HUD builder syntax check failed.' }

$work = Join-Path $repo 'build\v0.10.4\raven-compass-hud-three-payload'
if (Test-Path -LiteralPath $work) {
    Remove-Item -LiteralPath $work -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $work | Out-Null

$candidate = Join-Path $work 'r_ui.wad'
$reportRel = 'archive/field-logs/completionist-v104-raven-compass-hud-three-payload.json'
$report = Join-Path $repo ($reportRel -replace '/', '\')

Write-Host 'Building three-payload Raven compass HUD clone OFFLINE...'
& $python.Source $builder `
    --game-root $GameRoot `
    --output-wad $candidate `
    --report $report
if ($LASTEXITCODE -ne 0) { throw 'Offline Raven compass HUD build failed.' }

if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
    throw 'Candidate r_ui.wad was not created.'
}
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw 'Offline Raven HUD build report was not created.'
}

$liveWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
if ((Resolve-Path -LiteralPath $candidate).Path -eq (Resolve-Path -LiteralPath $liveWad).Path) {
    throw 'Candidate unexpectedly overlaps live r_ui.wad.'
}

$result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ([string]$result.result -ne 'OFFLINE_RAVEN_COMPASS_HUD_THREE_PAYLOAD_BUILT' -or
    [int]$result.builder_revision -ne 2 -or
    [string]$result.conclusion -ne 'THREE_PAYLOAD_RAVEN_HUD_CLONE_BUILT_OFFLINE' -or
    [int]$result.physical_payload_delta -ne 3 -or
    [int]$result.accounting_delta -ne 2 -or
    $result.game_files_written -ne $false -or
    $result.save_state_written -ne $false -or
    $result.progression_state_written -ne $false -or
    $result.marker_state_written -ne $false -or
    $result.proof.candidate_round_trip_byte_exact -ne $true -or
    $result.proof.three_new_payloads_only -ne $true -or
    $result.proof.root_type_accounting_delta_exactly_two -ne $true -or
    $result.proof.dependency_encoding_preserved_exactly -ne $true -or
    $result.proof.prototype_points_to_new_model -ne $true -or
    $result.proof.model_points_to_existing_raven_material -ne $true -or
    $result.proof.model_reuses_stock_dock_mesh -ne $true -or
    $result.proof.root_reuses_shared_compass_prototype -ne $true -or
    $result.proof.all_original_records_byte_identical_after_accounting_normalisation -ne $true -or
    $result.proof.stock_dock_resources_untouched -ne $true -or
    $result.proof.existing_raven_map_resources_untouched -ne $true -or
    $result.proof.ready_for_offline_dcb_iconname_gate -ne $true) {
    throw 'Offline Raven HUD candidate failed safety/result validation.'
}

$candidateSha = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
if ($candidateSha -ne [string]$result.candidate_wad_sha256) {
    throw 'Candidate r_ui.wad SHA256 does not match report.'
}

Write-Host ''
Write-Host 'Offline Raven compass HUD three-payload gate passed.'
Write-Host '- builder revision: 2 (dependency-encoding aware)'
Write-Host '- new payloads: gocompletionistravenhud, goProtoCompletionistRavenHUD, MDL_completionistravenhud'
Write-Host '- physical payload delta: +3'
Write-Host '- WAD_R_UI accounting delta: +2'
Write-Host ("- prototype -> model source encoding: inline={0}, zero-data-links={1}" -f $result.source_dependency_signatures.prototype_to_model.inline, $result.source_dependency_signatures.prototype_to_model.zero_data_links)
Write-Host ("- model -> material source encoding: inline={0}, zero-data-links={1}" -f $result.source_dependency_signatures.model_to_material.inline, $result.source_dependency_signatures.model_to_material.zero_data_links)
Write-Host ("- model -> mesh source encoding: inline={0}, zero-data-links={1}" -f $result.source_dependency_signatures.model_to_mesh.inline, $result.source_dependency_signatures.model_to_mesh.zero_data_links)
Write-Host '- Raven material reused: MAT_AE4AD85BB993F040'
Write-Host '- Dock mesh reused: MG_boatdock_0'
Write-Host '- shared compass reused: goProtocompassicons'
Write-Host ("- candidate: {0}" -f $candidate)
Write-Host ("- candidate SHA256: {0}" -f $candidateSha)
Write-Host ("- report: {0}" -f $report)
Write-Host '- game files written: false'
Write-Host '- DO NOT copy the candidate into the game yet.'

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Offline build report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive offline Raven HUD three-payload build' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Offline build report committed and pushed to $Remote/$branch."
    }
} finally {
    Pop-Location
}
