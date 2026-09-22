[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$ExpectedBranch = 'codex/collectible-legendary-chests'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    throw 'Not inside the Completionist Map repository.'
}
Set-Location $RepoRoot

$branch = (& git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    throw "Wrong branch '$branch'; expected '$ExpectedBranch'."
}
if (@(& git diff --cached --name-only).Count -gt 0) {
    throw 'Pre-existing staged changes exist; diagnostic install refused.'
}
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War before installing the temporary native route marker.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

$Builder = Join-Path $RepoRoot 'tools\v0.10.5\build-legendary-test-route-marker.py'
$RavenGuard = Join-Path $RepoRoot 'tools\v0.10.5\test-raven-frozen-baseline.ps1'
foreach ($required in @($Builder, $RavenGuard)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing required file: $required"
    }
}

& pwsh -NoProfile -ExecutionPolicy Bypass -File $RavenGuard
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven baseline guard failed.' }

$relativeFiles = @(
    'exec\dc\pc_le\mapmaster.dcb',
    'exec\dc\pc_le\mapcoords.dcb',
    'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
)
foreach ($relative in $relativeFiles) {
    $full = Join-Path $GameRoot $relative
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw "Missing installed file: $full"
    }
}

$backupRoot = Join-Path $GameRoot 'mods\completionist-map\diagnostic-backups\legendary-route-peak500'
if (Test-Path -LiteralPath $backupRoot) {
    throw "Diagnostic backup already exists: $backupRoot . Restore/remove the previous route marker first."
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$tempRoot = Join-Path $env:TEMP "completionist-legendary-route-$stamp"
$candidateRoot = Join-Path $tempRoot 'candidate'
$relativeEvidence = "archive/field-logs/runtime-captures/legendary-test-route-marker-install-$stamp"
$evidence = Join-Path $RepoRoot ($relativeEvidence -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $candidateRoot, $evidence | Out-Null

$console = Join-Path $evidence 'console-log.txt'
$transcriptStarted = $false
$installed = $false
$backedUp = $false
$installFailed = $false
$installFailureMessage = ''

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Restore-Backup {
    if (-not $script:backedUp) { return }
    foreach ($relative in $relativeFiles) {
        $backup = Join-Path $backupRoot $relative
        $target = Join-Path $GameRoot $relative
        if (Test-Path -LiteralPath $backup -PathType Leaf) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            [IO.File]::WriteAllBytes($target, [IO.File]::ReadAllBytes($backup))
        }
    }
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcriptStarted = $true

    Write-Host 'LEGENDARY TEST ROUTE MARKER - GUARDED INSTALL' -ForegroundColor Cyan
    Write-Host 'Target: tracked Legendary Chest peak500_chimneytop'
    Write-Host 'Purpose: temporary map + compass navigation only.'
    Write-Host 'Save/progression state is not read or written.'
    Write-Host ''

    & $python.Source $Builder --game-root $GameRoot --output-dir $candidateRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Diagnostic route candidate build failed with exit code $LASTEXITCODE."
    }

    $buildReportPath = Join-Path $candidateRoot 'legendary-route-report.json'
    if (-not (Test-Path -LiteralPath $buildReportPath -PathType Leaf)) {
        throw 'Diagnostic route builder did not produce its report.'
    }
    $report = Get-Content -LiteralPath $buildReportPath -Raw | ConvertFrom-Json
    if ([bool]$report.safety.save_or_progression_read -or
        [bool]$report.safety.save_or_progression_written -or
        [bool]$report.safety.collectible_state_inferred -or
        [bool]$report.safety.raven_progression_modified) {
        throw 'Diagnostic route safety contract changed.'
    }

    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    foreach ($relative in $relativeFiles) {
        $source = Join-Path $GameRoot $relative
        $backup = Join-Path $backupRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backup) | Out-Null
        [IO.File]::WriteAllBytes($backup, [IO.File]::ReadAllBytes($source))
    }
    $backedUp = $true

    $backupManifest = @{
        schema = 1
        installed_utc = (Get-Date).ToUniversalTime().ToString('o')
        branch = $ExpectedBranch
        target_catalogue_id = [string]$report.target.catalogue_id
        target_name = [string]$report.target.name
        target_uid_hex = [string]$report.target.uid_hex
        source_sha256 = $report.source_sha256
        candidate_sha256 = $report.candidate_sha256
        files = $relativeFiles
        diagnostic_only = $true
        save_or_progression_written = $false
    }
    $backupManifest | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (Join-Path $backupRoot 'manifest.json') -Encoding UTF8

    foreach ($relative in $relativeFiles) {
        $candidate = Join-Path $candidateRoot $relative
        $target = Join-Path $GameRoot $relative
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "Missing candidate file: $candidate"
        }
        [IO.File]::WriteAllBytes($target, [IO.File]::ReadAllBytes($candidate))
    }
    $installed = $true

    $installedHashes = @{}
    foreach ($relative in $relativeFiles) {
        $target = Join-Path $GameRoot $relative
        $installedHashes[$relative] = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    }

    $expectedMaster = [string]$report.candidate_sha256.'exec/dc/pc_le/mapmaster.dcb'
    $expectedCoords = [string]$report.candidate_sha256.'exec/dc/pc_le/mapcoords.dcb'
    $expectedLua = [string]$report.candidate_sha256.'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
    if ($installedHashes['exec\dc\pc_le\mapmaster.dcb'] -ne $expectedMaster -or
        $installedHashes['exec\dc\pc_le\mapcoords.dcb'] -ne $expectedCoords -or
        $installedHashes['mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'] -ne $expectedLua) {
        throw 'Installed diagnostic file hash verification failed.'
    }

    Copy-Item -LiteralPath $buildReportPath -Destination (Join-Path $evidence 'build-report.json') -Force
    @(
        "result=LEGENDARY_TEST_ROUTE_MARKER_INSTALLED"
        "target_catalogue_id=$($report.target.catalogue_id)"
        "target_name=$($report.target.name)"
        "target_uid_hex=$($report.target.uid_hex)"
        "target_world=$($report.target.world_position -join ',')"
        "backup_root=$backupRoot"
        "mapmaster_sha256=$($installedHashes['exec\dc\pc_le\mapmaster.dcb'])"
        "mapcoords_sha256=$($installedHashes['exec\dc\pc_le\mapcoords.dcb'])"
        "mapmenu_sha256=$($installedHashes['mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'])"
        'save_or_progression_read=false'
        'save_or_progression_written=false'
        'collectible_state_inferred=false'
        'raven_progression_modified=false'
        'diagnostic_route_only=true'
    ) | Set-Content -LiteralPath (Join-Path $evidence 'result.txt') -Encoding UTF8
}
catch {
    $message = $_.Exception.Message
    $script:installFailed = $true
    $script:installFailureMessage = $message
    if ($installed -or $backedUp) {
        try { Restore-Backup } catch {}
    }
    @(
        'result=LEGENDARY_TEST_ROUTE_MARKER_INSTALL_FAILED'
        "reason=$message"
        "rollback_attempted=$($backedUp.ToString().ToLowerInvariant())"
    ) | Set-Content -LiteralPath (Join-Path $evidence 'result.txt') -Encoding UTF8
}
finally {
    Stop-LocalTranscript
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

& git add -f -- $relativeEvidence
if ($LASTEXITCODE -ne 0) { throw 'git add diagnostic install evidence failed.' }
$commitMessage = if ($script:installFailed) {
    "research(v0.10.5): archive Legendary route marker install failure $stamp"
} else {
    "research(v0.10.5): install temporary Legendary route marker $stamp"
}
& git commit -m $commitMessage -- $relativeEvidence
if ($LASTEXITCODE -ne 0) { throw 'git commit diagnostic install evidence failed.' }
& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push diagnostic install evidence failed.' }
$head = (& git rev-parse HEAD).Trim()

if ($script:installFailed) {
    throw "Legendary route marker install failed; evidence pushed in $head. $($script:installFailureMessage)"
}

Write-Host ''
Write-Host "LEGENDARY_TEST_ROUTE_MARKER_PUSHED $head" -ForegroundColor Green
Write-Host 'Start God of War and load the same save.'
Write-Host 'Open the world map once. The diagnostic pin will be shown and automatically routed on the compass.'
Write-Host 'The diagnostic uses the Raven icon/class only as a proven navigation renderer; it does not change Raven progression.'
