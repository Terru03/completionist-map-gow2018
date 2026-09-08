param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if (-not $repo) { throw 'Run this from the completionist-map-gow2018 repository.' }
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected branch codex/v104-raven-hud-research, got '$branch'."
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

# Never let the report collector accidentally sweep unrelated staged work into
# its archival commit.
& git -C $repo diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    throw 'The Git index already contains staged changes. Commit/unstage them before running this read-only collector.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$script = Join-Path $repo 'tools\v0.10.4\inspect-compass-class-storage-registration.py'
$reportRel = 'archive/field-logs/completionist-v104-compass-class-storage-registration.json'
$report = Join-Path $repo ($reportRel -replace '/', [IO.Path]::DirectorySeparatorChar)
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Missing inspector: $script" }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $report) | Out-Null

& $python.Source $script --game-root $GameRoot --output $report
if ($LASTEXITCODE -ne 0) { throw 'CompassIconClass storage/registration inspection failed.' }

$result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ([string]$result.result -ne 'READ_ONLY_COMPASS_CLASS_STORAGE_REGISTRATION' -or
    $result.game_files_written -ne $false -or
    [string]$result.source_sha256 -ne 'eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039' -or
    [int]$result.compass_block.count -ne 9 -or
    [int]$result.record_size -ne 32) {
    throw 'Generated report failed validation gates.'
}

& git -C $repo add -- $reportRel
& git -C $repo diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Report unchanged; nothing to commit.'
    return
}

& git -C $repo commit -m 'Archive CompassIconClass storage registration scan'
if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
& git -C $repo push
if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }

Write-Host 'CompassIconClass storage/registration report committed and pushed.'
Write-Host 'No God of War files were modified.'
