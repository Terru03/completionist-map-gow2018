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
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War completely before building the Raven compass HUD offline candidate pair.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$testScript = Join-Path $PSScriptRoot 'test_compass_hud_physical_groups.py'
$scpScript = Join-Path $PSScriptRoot 'inspect-raven-compass-hud-scp-binding.py'
$wadScript = Join-Path $PSScriptRoot 'build-raven-compass-hud-four-payload.py'
$dcbScript = Join-Path $PSScriptRoot 'build-raven-compass-hud-dcb-offline.py'
$combinedScript = Join-Path $PSScriptRoot 'verify-raven-compass-hud-combined-offline.py'
$scripts = @($scpScript, $wadScript, $dcbScript, $combinedScript, $testScript)

foreach ($script in $scripts) {
    if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
        throw "Missing required script: $script"
    }
}

Write-Host 'Syntax-checking Raven compass HUD offline pipeline...'
foreach ($script in $scripts) {
    $sourceCode = [IO.File]::ReadAllText($script)
    $sourceCode | & $python.Source -c 'import ast,sys; ast.parse(sys.stdin.read())'
    if ($LASTEXITCODE -ne 0) { throw "Python syntax check failed: $script" }
}

Write-Host 'Running proven compass HUD physical-grammar tests...'
& $python.Source $testScript
if ($LASTEXITCODE -ne 0) { throw 'Compass HUD physical-grammar tests failed.' }

$archiveDir = Join-Path $repo 'archive\field-logs'
$buildDir = Join-Path $repo 'build\v0.10.4\raven-compass-hud-four-payload'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

$scpRel = 'archive/field-logs/completionist-v104-raven-compass-hud-scp-binding.json'
$wadRel = 'archive/field-logs/completionist-v104-raven-compass-hud-four-payload.json'
$dcbRel = 'archive/field-logs/completionist-v104-raven-compass-hud-dcb-offline.json'
$combinedRel = 'archive/field-logs/completionist-v104-raven-compass-hud-combined-offline.json'

$scpReportPath = Join-Path $repo ($scpRel -replace '/', '\')
$wadReportPath = Join-Path $repo ($wadRel -replace '/', '\')
$dcbReportPath = Join-Path $repo ($dcbRel -replace '/', '\')
$combinedReportPath = Join-Path $repo ($combinedRel -replace '/', '\')
$wadCandidate = Join-Path $buildDir 'r_ui.wad'
$dcbCandidate = Join-Path $buildDir 'wad_r_perm.dcb'

Write-Host ''
Write-Host '1/4 Tracing SCP binding semantics read-only...'
& $python.Source $scpScript --game-root $GameRoot --output $scpReportPath
if ($LASTEXITCODE -ne 0) { throw 'SCP binding inspection failed.' }
$scp = Get-Content -LiteralPath $scpReportPath -Raw | ConvertFrom-Json
if ([string]$scp.result -ne 'READ_ONLY_RAVEN_COMPASS_HUD_SCP_BINDING' -or
    [string]$scp.decision -ne 'LOCAL_SCP_REQUIRED' -or
    $scp.ready_for_offline_four_payload_builder -ne $true -or
    $scp.game_files_written -ne $false) {
    throw 'SCP binding gate did not prove LOCAL_SCP_REQUIRED.'
}

Write-Host ''
Write-Host '2/4 Building stock-shaped four-payload r_ui.wad candidate offline...'
& $python.Source $wadScript --game-root $GameRoot --output-wad $wadCandidate --report $wadReportPath
if ($LASTEXITCODE -ne 0) { throw 'Four-payload Raven HUD WAD build failed.' }
$wad = Get-Content -LiteralPath $wadReportPath -Raw | ConvertFrom-Json
if ([string]$wad.result -ne 'OFFLINE_RAVEN_COMPASS_HUD_FOUR_PAYLOAD_BUILT' -or
    [string]$wad.conclusion -ne 'FOUR_PAYLOAD_RAVEN_HUD_CLONE_BUILT_OFFLINE' -or
    $wad.clone_accounting.physical_records_delta -ne 13 -or
    $wad.clone_accounting.payload_records_delta -ne 4 -or
    $wad.clone_accounting.wad_r_ui_accounting_delta -ne 3 -or
    $wad.validation.local_scp_preserved_byte_exact -ne $true -or
    $wad.game_files_written -ne $false -or
    $wad.ready_for_offline_dcb_iconname_gate -ne $true) {
    throw 'Four-payload Raven HUD WAD report failed validation.'
}

Write-Host ''
Write-Host '3/4 Building CompletionistRaven DCB IconName binding offline...'
& $python.Source $dcbScript --game-root $GameRoot --output-dcb $dcbCandidate --report $dcbReportPath
if ($LASTEXITCODE -ne 0) { throw 'Dedicated Raven HUD DCB build failed.' }
$dcb = Get-Content -LiteralPath $dcbReportPath -Raw | ConvertFrom-Json
if ([string]$dcb.result -ne 'OFFLINE_PACKED_COMPLETIONIST_RAVEN_DEDICATED_HUD_BINDING_BUILT' -or
    [string]$dcb.visual_isolation.hud_IconName_after -ne '45E5C7943749F81C' -or
    [string]$dcb.visual_isolation.InWorld_tMPIcon_Name -ne '0E24C47DE2F769CA' -or
    $dcb.visual_isolation.changed_bytes_confined_to_raven_IconName -ne $true -or
    $dcb.visual_isolation.real_DockPoint_record_byte_identical -ne $true -or
    $dcb.game_files_written -ne $false -or
    $dcb.ready_for_combined_offline_contract_gate -ne $true) {
    throw 'Dedicated Raven HUD DCB report failed validation.'
}

Write-Host ''
Write-Host '4/4 Verifying WAD + DCB contract together against live pinned sources...'
& $python.Source $combinedScript --game-root $GameRoot --wad-candidate $wadCandidate --dcb-candidate $dcbCandidate --report $combinedReportPath
if ($LASTEXITCODE -ne 0) { throw 'Combined Raven HUD offline contract validation failed.' }
$combined = Get-Content -LiteralPath $combinedReportPath -Raw | ConvertFrom-Json
if ([string]$combined.result -ne 'OFFLINE_RAVEN_COMPASS_HUD_COMBINED_CONTRACT_PASSED' -or
    [string]$combined.conclusion -ne 'RAVEN_COMPASS_HUD_RUNTIME_CANDIDATE_READY' -or
    $combined.ready_for_reversible_runtime_install -ne $true -or
    $combined.safety.game_files_written -ne $false -or
    $combined.safety.runtime_test_performed -ne $false -or
    $combined.contract.map_GameObject_used_as_HUD_root -ne $false -or
    $combined.contract.local_SCP_preserved -ne $true) {
    throw 'Combined Raven HUD offline report failed validation.'
}

Write-Host ''
Write-Host 'Raven compass HUD offline candidate pair is validated.'
Write-Host '- SCP topology: LOCAL_SCP_REQUIRED'
Write-Host '- WAD clone: +13 physical / +4 payload / +3 WAD_R_UI accounting'
Write-Host '- DCB IconName: 45E5C7943749F81C (goCompletionistRavenHUD)'
Write-Host '- InWorld marker: stock DockPoint unchanged'
Write-Host ("- WAD SHA256: {0}" -f [string]$combined.wad_candidate.sha256)
Write-Host ("- DCB SHA256: {0}" -f [string]$combined.dcb_candidate.sha256)
Write-Host '- game files written: false'
Write-Host '- runtime test performed: false'
Write-Host '- next gate: reversible two-file install'
Write-Host ("- combined report: {0}" -f $combinedReportPath)

$reportRels = @($scpRel, $wadRel, $dcbRel, $combinedRel)
Push-Location $repo
try {
    git add -- $reportRels
    if ($LASTEXITCODE -ne 0) { throw 'git add reports failed.' }
    git diff --cached --check -- $reportRels
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    $staged = (& git diff --cached --name-only -- $reportRels) -join "`n"
    if ([string]::IsNullOrWhiteSpace($staged)) {
        Write-Host 'Offline Raven HUD reports unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive Raven HUD offline runtime candidate gate' -- $reportRels
        if ($LASTEXITCODE -ne 0) { throw 'git commit reports failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push reports failed.' }
        Write-Host "Reports committed and pushed to $Remote/$branch."
    }
} finally {
    Pop-Location
}
