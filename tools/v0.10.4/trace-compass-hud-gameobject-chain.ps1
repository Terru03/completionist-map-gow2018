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
    throw 'Close God of War completely before tracing the compass HUD GameObject chain.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
$script = Join-Path $PSScriptRoot 'trace-compass-hud-gameobject-chain.py'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Missing tracer: $script" }

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v104-compass-hud-gameobject-chain.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

Write-Host 'Syntax-checking compass HUD GameObject chain tracer...'
$source = [IO.File]::ReadAllText($script)
& $python.Source -c 'import ast,sys; ast.parse(sys.stdin.read())' <<< $source
if ($LASTEXITCODE -ne 0) { throw 'Compass HUD GameObject chain tracer syntax check failed.' }

Write-Host 'Tracing stock compass HUD GameObject resource chains read-only...'
& $python.Source $script --game-root $GameRoot --output $out
if ($LASTEXITCODE -ne 0) { throw 'Compass HUD GameObject chain trace failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw 'Compass HUD GameObject chain report was not created.' }

$report = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ([string]$report.result -ne 'READ_ONLY_COMPASS_HUD_GAMEOBJECT_CHAIN' -or
    $report.game_files_written -ne $false -or
    $report.save_state_written -ne $false -or
    $report.progression_state_written -ne $false -or
    $report.marker_state_written -ne $false -or
    [string]$report.conclusion -ne 'STOCK_COMPASS_HUD_GAMEOBJECT_CHAIN_TRACED') {
    throw 'Compass HUD GameObject chain report failed safety/result validation.'
}

$dock = $report.traces.DockPoint
Write-Host ''
Write-Host 'Compass HUD GameObject chain trace complete.'
Write-Host ("- stock HUD roots traced: {0}" -f @($report.traces.PSObject.Properties).Count)
Write-Host ("- Dock reachable definitions: {0}" -f $dock.reachable_definition_count)
Write-Host ("- Dock interesting resources: {0}" -f @($dock.interesting_resources).Count)
Write-Host ("- Dock reachable-ID backlinks: {0}" -f @($report.dock_reachable_id_backlinks).Count)
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
        Write-Host 'Compass HUD GameObject chain report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive compass HUD GameObject chain' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Report committed and pushed to $Remote/$branch."
    }
} finally {
    Pop-Location
}
