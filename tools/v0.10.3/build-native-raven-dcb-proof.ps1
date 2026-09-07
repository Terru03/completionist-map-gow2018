param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'research/v0.10.3-native-compass') {
    throw "Expected research/v0.10.3-native-compass, current branch is '$branch'."
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    throw 'Python 3.9+ is required.'
}

$reportRel = 'archive/field-logs/completionist-v103-dcb-build.json'
$report = Join-Path $repo ($reportRel -replace '/', '\')
$builder = Join-Path $PSScriptRoot 'build-native-raven-dcb-proof.py'

Write-Host ''
Write-Host 'Building OFFLINE v0.10.3 native Raven DCB proof...'
Write-Host 'This command reads the three stock DCB files but does not modify the game.'
Write-Host ''

& $python.Source $builder `
    --game-root $GameRoot `
    --repo-root $repo `
    --output $report
if ($LASTEXITCODE -ne 0) {
    throw "Offline DCB proof builder failed with exit code $LASTEXITCODE."
}

if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw "Expected report was not created: $report"
}

$reportJson = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($reportJson.result -ne 'OFFLINE_DCB_PROOF_BUILT_AND_REPARSED' -or
    $reportJson.game_files_written -ne $false -or
    $reportJson.compass_show_called -ne $false -or
    $reportJson.stock_source_hashes_unchanged -ne $true) {
    throw 'Offline proof report did not pass its required safety/result checks.'
}

Write-Host ''
Write-Host "Saved report: $report"
Write-Host "Candidate: $($reportJson.candidate.id)"
Write-Host "Patched markers: $($reportJson.patched_counts.map_records)"
Write-Host "Patched coordinates: $($reportJson.patched_counts.coordinates)"
Write-Host "Patched edges: $($reportJson.patched_counts.edges)"
Write-Host 'Game files written: False'
Write-Host 'Compass.ShowMarker called: False'

& git -C $repo add -- $reportRel
if ($LASTEXITCODE -ne 0) {
    throw 'git add failed for offline DCB proof report.'
}

& git -C $repo diff --cached --check -- $reportRel
if ($LASTEXITCODE -ne 0) {
    throw 'git diff --cached --check failed for offline DCB proof report.'
}

& git -C $repo diff --cached --quiet -- $reportRel
$hasChanges = $LASTEXITCODE -ne 0
if (-not $hasChanges) {
    Write-Host 'Report unchanged. Nothing to commit or push.'
    return
}

& git -C $repo commit -m 'Archive offline native Raven DCB proof' -- $reportRel
if ($LASTEXITCODE -ne 0) {
    throw 'git commit failed for offline DCB proof report.'
}

& git -C $repo push $Remote $branch
if ($LASTEXITCODE -ne 0) {
    throw "git push failed. Report commit exists locally on '$branch'."
}

Write-Host "Pushed offline DCB proof report to $Remote/$branch"
Write-Host ''
Write-Host 'Do NOT copy build/v0.10.3-dcb-proof files into the game yet.'
