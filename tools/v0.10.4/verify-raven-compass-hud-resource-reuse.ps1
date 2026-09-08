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
    throw 'Close God of War completely before verifying Raven compass HUD resource reuse.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
$script = Join-Path $PSScriptRoot 'verify-raven-compass-hud-resource-reuse.py'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Missing verifier: $script" }

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v104-raven-compass-hud-resource-reuse.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

Write-Host 'Syntax-checking Raven compass HUD resource reuse verifier...'
$sourceCode = [IO.File]::ReadAllText($script)
$sourceCode | & $python.Source -c 'import ast,sys; ast.parse(sys.stdin.read())'
if ($LASTEXITCODE -ne 0) { throw 'Raven compass HUD resource reuse verifier syntax check failed.' }

Write-Host 'Verifying current Raven artwork can be reused by a compass-only HUD clone read-only...'
& $python.Source $script --game-root $GameRoot --output $out
if ($LASTEXITCODE -ne 0) { throw 'Raven compass HUD resource reuse verification failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw 'Raven compass HUD resource reuse report was not created.' }

$report = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ([string]$report.result -ne 'READ_ONLY_RAVEN_COMPASS_HUD_REUSE_GATE' -or
    $report.game_files_read -ne $true -or
    $report.game_files_written -ne $false -or
    $report.save_state_written -ne $false -or
    $report.progression_state_written -ne $false -or
    $report.marker_state_written -ne $false -or
    $report.reuse_decision.minimal_new_payload_count -ne 3 -or
    [string]$report.conclusion -ne 'EXISTING_RAVEN_ARTWORK_REUSABLE_FOR_COMPASS_HUD') {
    throw 'Raven compass HUD resource reuse report failed safety/result validation.'
}

Write-Host ''
Write-Host 'Raven compass HUD resource reuse gate complete.'
Write-Host ("- current r_ui.wad: {0}" -f [string]$report.r_ui_wad_sha256)
Write-Host ("- Raven material reusable: {0}" -f [string]$report.existing_raven_artwork.material.name)
Write-Host ("- stock mesh reusable: {0}" -f [string]$report.stock_hud_contract.mesh.name)
Write-Host ("- minimal new payloads: {0}" -f [string]$report.reuse_decision.minimal_new_payload_count)
Write-Host ("- proposed HUD IconName hash: {0}" -f [string]$report.proposed_compass_hud_identity.IconName_hash)
Write-Host ("- conclusion: {0}" -f [string]$report.conclusion)
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
        Write-Host 'Raven compass HUD resource reuse report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive Raven compass HUD resource reuse gate' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Report committed and pushed to $Remote/$branch."
    }
} finally {
    Pop-Location
}
