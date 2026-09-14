param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedBranch = 'codex/all-collectibles-production-research'
$expectedExeSha = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/runtime-captures/raven-gameobject-identity-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$targetPath = Join-Path $GameRoot 'mods\lua\gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$probePath = Join-Path $repo 'tools\v0.10.5\raven-gameobject-identity-probe.lua'
$loaderLogPath = Join-Path $GameRoot 'mods\loader_log.txt'
$exePath = Join-Path $GameRoot 'GoW.exe'
$tempBackup = Join-Path $env:TEMP ("completionist-identity-$stamp.bak")
$targetRestored = $false
$transcriptStarted = $false
$published = $false
$gameLaunched = $false
$probeOutputFound = $false
$beforeLines = @()

function Stop-LocalTranscript {
    if ($script:transcriptStarted) { Stop-Transcript | Out-Null; $script:transcriptStarted = $false }
}
function Restore-Target {
    if ($script:targetRestored) { return }
    if (Test-Path -LiteralPath $tempBackup -PathType Leaf) {
        [IO.File]::WriteAllBytes($targetPath, [IO.File]::ReadAllBytes($tempBackup))
        $script:targetRestored = $true
    }
}
function Write-Result([string]$result) {
    @(
        "result=$result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        "game_launched=$($script:gameLaunched.ToString().ToLowerInvariant())"
        "target_restored=$($script:targetRestored.ToString().ToLowerInvariant())"
        "probe_output_found=$($script:probeOutputFound.ToString().ToLowerInvariant())"
        'probe_read_only=true'
        'probe_save_writes=false'
        'probe_progression_writes=false'
        'probe_streaming_writes=false'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8
}
function Publish([string]$result) {
    if ($script:published) { return }
    Stop-LocalTranscript
    Write-Result $result
    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Archive Raven GameObject identity probe $stamp" -- $relativeLogDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin "HEAD:$expectedBranch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged capture.' }
    $script:published = $true
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Completionist Map Raven GameObject identity probe ==='
    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }
    $staged = @(& git diff --cached --name-only)
    if ($staged.Count -gt 0) { throw "Refusing staged changes: $($staged -join ', ')" }
    foreach ($path in @($targetPath, $probePath, $exePath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing file: $path" }
    }
    if (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }) {
        throw 'God of War is already running.'
    }
    $exeSha = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($exeSha -ne $expectedExeSha) { throw "Unsupported GoW.exe SHA-256: $exeSha" }

    $originalBytes = [IO.File]::ReadAllBytes($targetPath)
    [IO.File]::WriteAllBytes($tempBackup, $originalBytes)
    $originalHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $probeText = [IO.File]::ReadAllText($probePath, [Text.Encoding]::UTF8)
    if ([Text.Encoding]::UTF8.GetString($originalBytes).Contains('BEGIN COMPLETIONIST RAVEN GAMEOBJECT IDENTITY PROBE')) {
        throw 'Target already contains identity probe.'
    }
    $append = [Text.Encoding]::UTF8.GetBytes("`r`n" + $probeText.Replace("`n", "`r`n"))
    $combined = New-Object byte[] ($originalBytes.Length + $append.Length)
    [Array]::Copy($originalBytes, 0, $combined, 0, $originalBytes.Length)
    [Array]::Copy($append, 0, $combined, $originalBytes.Length, $append.Length)
    [IO.File]::WriteAllBytes($targetPath, $combined)

    if (Test-Path -LiteralPath $loaderLogPath) { $beforeLines = @(Get-Content -LiteralPath $loaderLogPath) }
    Write-Host 'Probe installed. Load the Veithurgard 2/3 save, wait until the Raven script restores, touch nothing, then quit fully.' -ForegroundColor Cyan
    Start-Process -FilePath $exePath -WorkingDirectory $GameRoot | Out-Null
    $gameLaunched = $true
    while ($true) {
        Read-Host 'After God of War fully exits, press Enter' | Out-Null
        $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') })
        if ($running.Count -eq 0) { break }
        Write-Host 'God of War is still running.' -ForegroundColor Yellow
    }

    $afterLines = @(Get-Content -LiteralPath $loaderLogPath)
    Copy-Item -LiteralPath $loaderLogPath -Destination (Join-Path $logDir 'loader_log.txt') -Force
    $fresh = $afterLines
    $prefixMatches = $beforeLines.Count -le $afterLines.Count
    if ($prefixMatches) {
        for ($i=0; $i -lt $beforeLines.Count; $i++) {
            if ($beforeLines[$i] -cne $afterLines[$i]) { $prefixMatches = $false; break }
        }
    }
    if ($prefixMatches -and $beforeLines.Count -gt 0) { $fresh = @($afterLines | Select-Object -Skip $beforeLines.Count) }
    $probeLines = @($fresh | Select-String -SimpleMatch '[CompletionistIdentityProbe]' | ForEach-Object { $_.Line })
    if ($probeLines.Count -gt 0) {
        $probeOutputFound = $true
        $probeLines | Set-Content -LiteralPath (Join-Path $logDir 'probe-extract.txt') -Encoding UTF8
    } else {
        'NO_COMPLETIONIST_IDENTITY_PROBE_LINES_FOUND' | Set-Content -LiteralPath (Join-Path $logDir 'probe-extract.txt') -Encoding UTF8
    }

    Restore-Target
    $restoredHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()
    @(
        "precisionchallenge_before_sha256=$originalHash"
        "precisionchallenge_after_restore_sha256=$restoredHash"
        "exact_restore=$($restoredHash -eq $originalHash)"
    ) | Set-Content -LiteralPath (Join-Path $logDir 'restore-verification.txt') -Encoding UTF8
    if ($restoredHash -ne $originalHash) { throw 'Target restore hash mismatch.' }

    Publish $(if ($probeOutputFound) { 'RAVEN_GAMEOBJECT_IDENTITY_CAPTURED' } else { 'RAVEN_GAMEOBJECT_IDENTITY_NO_SIGNAL' })
    Write-Host $(if ($probeOutputFound) { 'RAVEN_GAMEOBJECT_IDENTITY_CAPTURED_AND_PUSHED' } else { 'RAVEN_GAMEOBJECT_IDENTITY_NO_SIGNAL_AND_PUSHED' }) -ForegroundColor Green
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    try { Restore-Target } catch {}
    try { Publish 'RAVEN_GAMEOBJECT_IDENTITY_PROBE_FAILED' } catch {}
    throw
}
finally {
    try { Restore-Target } catch {}
    if (Test-Path -LiteralPath $tempBackup) { Remove-Item -LiteralPath $tempBackup -Force -ErrorAction SilentlyContinue }
    Stop-LocalTranscript
}
