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
$script = Join-Path $PSScriptRoot 'verify-raven-compass-hud-wad-accounting.py'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Missing verifier: $script" }

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v104-raven-compass-hud-wad-accounting.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

Write-Host 'Syntax-checking Raven compass HUD WAD accounting verifier...'
$sourceCode = [IO.File]::ReadAllText($script)
$sourceCode | & $python.Source -c 'import ast,sys; ast.parse(sys.stdin.read())'
if ($LASTEXITCODE -ne 0) { throw 'Raven compass HUD WAD accounting verifier syntax check failed.' }

Write-Host 'Verifying current r_ui.wad accounting for the three-payload HUD clone...'
& $python.Source $script --game-root $GameRoot --output $out
if ($LASTEXITCODE -ne 0) { throw 'Raven compass HUD WAD accounting verification failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw 'Accounting report was not created.' }

$report = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ([string]$report.result -ne 'READ_ONLY_RAVEN_COMPASS_HUD_WAD_ACCOUNTING' -or
    $report.game_files_written -ne $false -or
    $report.save_state_written -ne $false -or
    $report.progression_state_written -ne $false -or
    $report.marker_state_written -ne $false -or
    $report.source_round_trip_byte_exact -ne $true -or
    $report.proof.ready_for_offline_three_payload_builder -ne $true -or
    [int]$report.three_payload_clone_plan.physical_payload_delta -ne 3 -or
    [int]$report.three_payload_clone_plan.root_type_accounting_delta -ne 2 -or
    [string]$report.conclusion -ne 'THREE_PAYLOAD_RAVEN_HUD_WAD_ACCOUNTING_PROVEN') {
    throw 'Raven compass HUD WAD accounting report failed safety/result validation.'
}

Write-Host ''
Write-Host 'Raven compass HUD WAD accounting gate passed.'
Write-Host '- physical clone payloads: 3'
Write-Host '- WAD_R_UI type-accounting delta: 2'
Write-Host '- goProtoCompletionistRavenHUD: +1 to 0x10001'
Write-Host '- gocompletionistravenhud: +1 to 0x20001'
Write-Host '- MDL_completionistravenhud: no root type-table increment'
Write-Host ("- report: {0}" -f $out)
Write-Host '- game files written: false'

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Accounting report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive Raven HUD WAD accounting gate' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Accounting report committed and pushed to $Remote/$branch."
    }
} finally {
    Pop-Location
}
