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
$relativeLogDir = "archive/field-logs/runtime-captures/native-namespace-inventory-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$mapRestored = $false
$published = $false
$transcriptStarted = $false
$probeOutputFound = $false
$gameLaunched = $false

$mapRelative = 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$probeRelative = 'tools\v0.10.5\generic-native-namespace-inventory.lua'
$mapPath = Join-Path $GameRoot $mapRelative
$probePath = Join-Path $repo $probeRelative
$loaderLogPath = Join-Path $GameRoot 'mods\loader_log.txt'
$exePath = Join-Path $GameRoot 'GoW.exe'
$tempBackup = Join-Path $env:TEMP ("completionist-namespace-mapmenu-$stamp.bak")

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Restore-MapMenu {
    if ($script:mapRestored) { return }
    if (Test-Path -LiteralPath $tempBackup -PathType Leaf) {
        [IO.File]::WriteAllBytes($mapPath, [IO.File]::ReadAllBytes($tempBackup))
        $script:mapRestored = $true
    }
}

function Write-Result([string]$result) {
    @(
        "result=$result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        "game_launched=$($script:gameLaunched.ToString().ToLowerInvariant())"
        "mapmenu_restored=$($script:mapRestored.ToString().ToLowerInvariant())"
        "probe_output_found=$($script:probeOutputFound.ToString().ToLowerInvariant())"
        'native_candidate_calls=false'
        'probe_progression_writes=false'
        'helper_save_writes=false'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8
}

function Publish-Capture([string]$result) {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    Write-Result $result
    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 0) { return }
    if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged capture.' }
    & git commit -m "Archive native namespace inventory $stamp" -- $relativeLogDir | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    & git push origin "HEAD:$expectedBranch" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map native namespace inventory ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"
    Write-Host "Loader log: $loaderLogPath"
    Write-Host 'Probe behavior: namespace/metatable name and type enumeration only. No native candidate calls and no progression writes.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch. Expected '$expectedBranch', found '$branch'." }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing to run with staged changes: $($staged -join ', ')" }

    foreach ($path in @($mapPath, $probePath, $exePath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
    }
    if (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }) {
        throw 'God of War is already running. Close it first.'
    }

    $originalBytes = [IO.File]::ReadAllBytes($mapPath)
    [IO.File]::WriteAllBytes($tempBackup, $originalBytes)
    $originalHash = (Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $probeHash = (Get-FileHash -LiteralPath $probePath -Algorithm SHA256).Hash.ToLowerInvariant()

    $probeText = [IO.File]::ReadAllText($probePath, [Text.Encoding]::UTF8)
    if ([Text.Encoding]::UTF8.GetString($originalBytes).Contains('BEGIN COMPLETIONIST GENERIC NATIVE NAMESPACE INVENTORY')) {
        throw 'mapmenu.lua already contains the namespace probe marker.'
    }

    $appendBytes = [Text.Encoding]::UTF8.GetBytes("`r`n" + $probeText.Replace("`n", "`r`n"))
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
        'native_candidate_calls=false'
        'probe_progression_writes=false'
        'helper_save_writes=false'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'installed-file-hashes.txt') -Encoding UTF8

    Write-Host ''
    Write-Host 'Probe installed temporarily.'
    Write-Host 'Load the existing save, open the world map, move the map cursor once, then quit God of War completely.' -ForegroundColor Cyan
    Write-Host 'Do not collect/kill/open anything during this probe.' -ForegroundColor Cyan
    Write-Host 'After the game is fully closed, return here and press Enter.' -ForegroundColor Cyan
    Write-Host ''

    Start-Process -FilePath $exePath -WorkingDirectory $GameRoot | Out-Null
    $gameLaunched = $true
    Read-Host 'Press Enter ONLY after God of War is fully closed' | Out-Null

    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') })
    if ($running.Count -gt 0) { throw 'God of War is still running. Close it completely, then rerun the probe.' }

    if (Test-Path -LiteralPath $loaderLogPath -PathType Leaf) {
        Copy-Item -LiteralPath $loaderLogPath -Destination (Join-Path $logDir 'loader_log.txt') -Force
        $probeLines = @(Select-String -LiteralPath $loaderLogPath -SimpleMatch '[CompletionistNamespaceProbe]' | ForEach-Object { $_.Line })
        if ($probeLines.Count -gt 0) {
            $probeOutputFound = $true
            $probeLines | Set-Content -LiteralPath (Join-Path $logDir 'probe-extract.txt') -Encoding UTF8
            Write-Host "Captured $($probeLines.Count) namespace probe lines."
        } else {
            'NO_COMPLETIONIST_NAMESPACE_PROBE_LINES_FOUND' | Set-Content -LiteralPath (Join-Path $logDir 'probe-extract.txt') -Encoding UTF8
            Write-Host 'No namespace probe lines found.' -ForegroundColor Yellow
        }
    } else {
        'LOADER_LOG_NOT_FOUND' | Set-Content -LiteralPath (Join-Path $logDir 'probe-extract.txt') -Encoding UTF8
        Write-Host "Loader log not found: $loaderLogPath" -ForegroundColor Yellow
    }

    Restore-MapMenu
    $restoredHash = (Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash.ToLowerInvariant()
    @(
        "mapmenu_before_sha256=$originalHash"
        "mapmenu_after_restore_sha256=$restoredHash"
        "exact_restore=$($restoredHash -eq $originalHash)"
    ) | Set-Content -LiteralPath (Join-Path $logDir 'restore-verification.txt') -Encoding UTF8
    if ($restoredHash -ne $originalHash) { throw 'mapmenu.lua restore hash mismatch.' }

    if ($probeOutputFound) {
        Publish-Capture 'NAMESPACE_INVENTORY_CAPTURED'
        Write-Host 'NAMESPACE_INVENTORY_CAPTURED_AND_PUSHED'
    } else {
        Publish-Capture 'NAMESPACE_INVENTORY_NO_OUTPUT'
        Write-Host 'NAMESPACE_INVENTORY_NO_OUTPUT_PUSHED' -ForegroundColor Yellow
    }
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "NAMESPACE_INVENTORY_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Restore-MapMenu } catch {}
    try { Publish-Capture 'NAMESPACE_INVENTORY_FAILED' } catch { Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    try { Restore-MapMenu } catch {}
    if (Test-Path -LiteralPath $tempBackup) { Remove-Item -LiteralPath $tempBackup -Force -ErrorAction SilentlyContinue }
    Stop-LocalTranscript
}
