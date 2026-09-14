param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/runtime-captures/generic-counter-runtime-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$published = $false
$transcriptStarted = $false
$mapRestored = $false
$gameLaunched = $false
$probeOutputFound = $false

$mapRelative = 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$probeRelative = 'tools\v0.10.5\generic-counter-runtime-probe.lua'
$mapPath = Join-Path $GameRoot $mapRelative
$probePath = Join-Path $repo $probeRelative
$loaderLogPath = Join-Path $GameRoot 'mods\loader_log.txt'
$exePath = Join-Path $GameRoot 'GoW.exe'
$tempBackup = Join-Path $env:TEMP ("completionist-mapmenu-$stamp.bak")

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Write-Result([string]$Result) {
    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        "game_launched=$($script:gameLaunched.ToString().ToLowerInvariant())"
        "mapmenu_restored=$($script:mapRestored.ToString().ToLowerInvariant())"
        "probe_output_found=$($script:probeOutputFound.ToString().ToLowerInvariant())"
        'probe_progression_writes=false'
        'helper_save_writes=false'
        'normal_game_save_activity_not_blocked=true'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8
}

function Publish-Capture([string]$Result) {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    Write-Result $Result
    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add of capture directory failed.' }
    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 0) { return }
    if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged capture changes.' }
    & git commit -m "Archive generic counter runtime probe $stamp" -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git commit of runtime capture failed.' }
    & git push origin "HEAD:$expectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'git push of runtime capture failed.' }
}

function Restore-MapMenu {
    if ($script:mapRestored) { return }
    if (Test-Path -LiteralPath $tempBackup -PathType Leaf) {
        [IO.File]::WriteAllBytes($mapPath, [IO.File]::ReadAllBytes($tempBackup))
        $script:mapRestored = $true
    }
}

function Wait-ForConfirmedGameExit {
    while ($true) {
        Read-Host 'After God of War has fully exited, press Enter to capture the log and restore mapmenu.lua' | Out-Null
        $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') })
        if ($running.Count -eq 0) { return }
        Write-Host 'God of War is still running. Quit the game completely before continuing.' -ForegroundColor Yellow
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map generic counter runtime probe ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"
    Write-Host "Loader log: $loaderLogPath"
    Write-Host 'Probe behavior: read-only API introspection and counter reads only. No setters, SaveGame, quest writes, or progression writes.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch. Expected '$expectedBranch', found '$branch'." }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect pre-existing staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')" }

    if (-not (Test-Path -LiteralPath $mapPath -PathType Leaf)) { throw "mapmenu.lua not found: $mapPath" }
    if (-not (Test-Path -LiteralPath $probePath -PathType Leaf)) { throw "Probe Lua not found: $probePath" }
    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) { throw "GoW.exe not found: $exePath" }
    if (Get-Process -Name 'GoW' -ErrorAction SilentlyContinue) { throw 'GoW is already running. Close it before starting this probe.' }

    $originalBytes = [IO.File]::ReadAllBytes($mapPath)
    [IO.File]::WriteAllBytes($tempBackup, $originalBytes)
    $originalHash = (Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $probeHash = (Get-FileHash -LiteralPath $probePath -Algorithm SHA256).Hash.ToLowerInvariant()

    $probeText = [IO.File]::ReadAllText($probePath, [Text.Encoding]::UTF8)
    if ([Text.Encoding]::UTF8.GetString($originalBytes).Contains('BEGIN COMPLETIONIST GENERIC COUNTER RUNTIME PROBE')) {
        throw 'mapmenu.lua already contains the generic counter runtime probe marker.'
    }

    $appendText = "`r`n" + $probeText.Replace("`n", "`r`n")
    $appendBytes = [Text.Encoding]::UTF8.GetBytes($appendText)
    $combined = New-Object byte[] ($originalBytes.Length + $appendBytes.Length)
    [Array]::Copy($originalBytes, 0, $combined, 0, $originalBytes.Length)
    [Array]::Copy($appendBytes, 0, $combined, $originalBytes.Length, $appendBytes.Length)
    [IO.File]::WriteAllBytes($mapPath, $combined)
    $installedHash = (Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash.ToLowerInvariant()

    @(
        "mapmenu_before_sha256=$originalHash"
        "mapmenu_probe_installed_sha256=$installedHash"
        "probe_lua_sha256=$probeHash"
        "mapmenu_path=$mapPath"
        "loader_log_path=$loaderLogPath"
        'probe_progression_writes=false'
        'helper_save_writes=false'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'installed-file-hashes.txt') -Encoding UTF8

    Write-Host ''
    Write-Host 'The probe is installed temporarily.'
    Write-Host 'In the game: load your existing save, open the world map, move the map cursor once, then quit God of War completely.' -ForegroundColor Cyan
    Write-Host 'Do not collect/kill/open anything during this probe.' -ForegroundColor Cyan
    Write-Host 'The runner will keep mapmenu.lua patched until YOU press Enter after the game is fully closed.' -ForegroundColor Cyan
    Write-Host ''

    Start-Process -FilePath $exePath -WorkingDirectory $GameRoot | Out-Null
    $gameLaunched = $true
    Wait-ForConfirmedGameExit

    if (Test-Path -LiteralPath $loaderLogPath -PathType Leaf) {
        Copy-Item -LiteralPath $loaderLogPath -Destination (Join-Path $logDir 'loader_log.txt') -Force
        $probeLines = @(Select-String -LiteralPath $loaderLogPath -SimpleMatch '[CompletionistCounterProbe]' | ForEach-Object { $_.Line })
        if ($probeLines.Count -gt 0) {
            $probeOutputFound = $true
            $probeLines | Set-Content -LiteralPath (Join-Path $logDir 'probe-extract.txt') -Encoding UTF8
            Write-Host "Captured $($probeLines.Count) probe log lines."
        } else {
            'NO_COMPLETIONIST_COUNTER_PROBE_LINES_FOUND' | Set-Content -LiteralPath (Join-Path $logDir 'probe-extract.txt') -Encoding UTF8
            Write-Host 'No probe lines were found in mods\loader_log.txt.' -ForegroundColor Yellow
        }
    } else {
        'LOADER_LOG_NOT_FOUND' | Set-Content -LiteralPath (Join-Path $logDir 'probe-extract.txt') -Encoding UTF8
        Write-Host "loader_log.txt not found at $loaderLogPath" -ForegroundColor Yellow
    }

    Restore-MapMenu
    $restoredHash = (Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($restoredHash -ne $originalHash) { throw "mapmenu.lua restore hash mismatch. Expected $originalHash, found $restoredHash" }

    @(
        "mapmenu_before_sha256=$originalHash"
        "mapmenu_after_restore_sha256=$restoredHash"
        "exact_restore=$($restoredHash -eq $originalHash)"
    ) | Set-Content -LiteralPath (Join-Path $logDir 'restore-verification.txt') -Encoding UTF8

    if ($probeOutputFound) {
        Publish-Capture 'RUNTIME_PROBE_CAPTURED'
        Write-Host 'RUNTIME_PROBE_CAPTURED_AND_PUSHED'
    } else {
        Publish-Capture 'RUNTIME_PROBE_NO_OUTPUT'
        Write-Host 'RUNTIME_PROBE_NO_OUTPUT_PUSHED' -ForegroundColor Yellow
    }
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "RUNTIME_PROBE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Restore-MapMenu } catch {
        try { $_.Exception.ToString() | Add-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    }
    try { Publish-Capture 'RUNTIME_PROBE_FAILED' } catch { Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    try { Restore-MapMenu } catch {}
    if (Test-Path -LiteralPath $tempBackup) { Remove-Item -LiteralPath $tempBackup -Force -ErrorAction SilentlyContinue }
    Stop-LocalTranscript
}