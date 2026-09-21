param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $RepoRoot

$branch = (& git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) { throw "Wrong branch '$branch'; expected '$ExpectedBranch'." }
if (@(& git diff --cached --name-only).Count -gt 0) { throw 'Pre-existing staged changes exist; probe refused.' }

$targetRelative = 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$target = Join-Path $GameRoot $targetRelative
$probe = Join-Path $RepoRoot 'tools\v0.10.5\raven-native-bridge-probe.lua'
$dllSource = Join-Path $RepoRoot 'native\v0.10.5\completionist_raven_authority_probe.dll'
$dllDir = Join-Path $GameRoot 'mods\completionist_map'
$dllTarget = Join-Path $dllDir 'completionist_raven_authority_probe.dll'
$loaderLog = Join-Path $GameRoot 'mods\loader_log.txt'
$exe = Join-Path $GameRoot 'GoW.exe'
$expectedExeHash = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
$expectedDllHash = 'ba66ad78fb6851d79419591b962858c2cd14492ea4be5ee6c56cc060d34137eb'

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-native-bridge-probe-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$console = Join-Path $outDir 'console-log.txt'
$extract = Join-Path $outDir 'probe-extract.txt'
$resultFile = Join-Path $outDir 'result.txt'
$mapBackup = Join-Path $env:TEMP "completionist-raven-mapmenu-$stamp.bak"
$dllBackup = Join-Path $env:TEMP "completionist-raven-bridge-$stamp.dll.bak"

$mapRestored = $false
$dllRestored = $false
$dllExisted = $false
$published = $false
$transcript = $false
$launched = $false

function Restore-LocalState {
    if (-not $script:mapRestored -and (Test-Path -LiteralPath $mapBackup -PathType Leaf)) {
        [IO.File]::WriteAllBytes($target, [IO.File]::ReadAllBytes($mapBackup))
        $script:mapRestored = $true
    }
    if (-not $script:dllRestored) {
        if ($script:dllExisted -and (Test-Path -LiteralPath $dllBackup -PathType Leaf)) {
            New-Item -ItemType Directory -Force -Path $dllDir | Out-Null
            [IO.File]::WriteAllBytes($dllTarget, [IO.File]::ReadAllBytes($dllBackup))
        } elseif (Test-Path -LiteralPath $dllTarget -PathType Leaf) {
            Remove-Item -LiteralPath $dllTarget -Force
        }
        $script:dllRestored = $true
    }
}

function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
}

function Publish-Capture([string]$result) {
    if ($script:published) { return }
    Stop-LocalTranscript
    @(
        "result=$result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$ExpectedBranch"
        "game_launched=$($script:launched.ToString().ToLowerInvariant())"
        "mapmenu_restored=$($script:mapRestored.ToString().ToLowerInvariant())"
        "bridge_dll_restored=$($script:dllRestored.ToString().ToLowerInvariant())"
        'probe_process_memory_writes=false'
        'probe_save_writes=false'
        'probe_progression_writes=false'
        'probe_game_file_persistence=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8

    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relativeDir
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "research(v0.10.5): capture Raven native Lua bridge probe $stamp" -- $relativeDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin $ExpectedBranch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff --cached failed.'
    }
    $script:published = $true
}

try {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true

    foreach ($path in @($target, $probe, $dllSource, $exe)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required file: $path" }
    }
    if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
        throw 'Close God of War before running this bridge probe.'
    }
    $exeHash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($exeHash -ne $expectedExeHash) { throw "GoW.exe SHA mismatch: $exeHash" }
    $dllHash = (Get-FileHash -LiteralPath $dllSource -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($dllHash -ne $expectedDllHash) { throw "Bridge probe DLL SHA mismatch: $dllHash" }

    $mapBefore = [IO.File]::ReadAllBytes($target)
    [IO.File]::WriteAllBytes($mapBackup, $mapBefore)
    $mapBeforeHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    $mapText = [Text.Encoding]::UTF8.GetString($mapBefore)
    if ($mapText.Contains('BEGIN COMPLETIONIST V0.10.5 RAVEN NATIVE BRIDGE PROBE')) {
        throw 'Native bridge probe already present in mapmenu.lua.'
    }

    $script:dllExisted = Test-Path -LiteralPath $dllTarget -PathType Leaf
    if ($script:dllExisted) {
        [IO.File]::WriteAllBytes($dllBackup, [IO.File]::ReadAllBytes($dllTarget))
    }
    New-Item -ItemType Directory -Force -Path $dllDir | Out-Null
    Copy-Item -LiteralPath $dllSource -Destination $dllTarget -Force

    $probeText = [IO.File]::ReadAllText($probe, [Text.Encoding]::UTF8)
    $appendText = [Environment]::NewLine + $probeText.Replace([char]10, [Environment]::NewLine)
    $append = [Text.Encoding]::UTF8.GetBytes($appendText)
    $combined = New-Object byte[] ($mapBefore.Length + $append.Length)
    [Array]::Copy($mapBefore, 0, $combined, 0, $mapBefore.Length)
    [Array]::Copy($append, 0, $combined, $mapBefore.Length, $append.Length)
    [IO.File]::WriteAllBytes($target, $combined)

    @(
        "mapmenu_before_sha256=$mapBeforeHash"
        "mapmenu_probe_sha256=$((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant())"
        "probe_lua_sha256=$((Get-FileHash -LiteralPath $probe -Algorithm SHA256).Hash.ToLowerInvariant())"
        "bridge_dll_sha256=$dllHash"
        "bridge_dll_target=$dllTarget"
        "bridge_dll_preexisting=$($script:dllExisted.ToString().ToLowerInvariant())"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'installed-file-hashes.txt') -Encoding UTF8

    $beforeLines = @()
    if (Test-Path -LiteralPath $loaderLog -PathType Leaf) {
        $beforeLines = @(Get-Content -LiteralPath $loaderLog)
    }

    Write-Host 'RAVEN NATIVE LUA BRIDGE PROBE'
    Write-Host 'The probe only verifies package.loadlib + Lua C boolean return ABI.'
    Write-Host 'No save needs to be loaded.'
    Write-Host 'God of War will launch now. Let it reach the main menu, then quit fully.'
    Start-Process -FilePath $exe -WorkingDirectory $GameRoot | Out-Null
    $launched = $true

    while ($true) {
        Read-Host 'After God of War has fully exited, press Enter' | Out-Null
        if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -eq 0) { break }
        Write-Host 'God of War is still running. Quit it fully first.' -ForegroundColor Yellow
    }

    $fresh = @()
    if (Test-Path -LiteralPath $loaderLog -PathType Leaf) {
        Copy-Item -LiteralPath $loaderLog -Destination (Join-Path $outDir 'loader_log.txt') -Force
        $afterLines = @(Get-Content -LiteralPath $loaderLog)
        $prefixMatches = $beforeLines.Count -le $afterLines.Count
        if ($prefixMatches) {
            for ($i = 0; $i -lt $beforeLines.Count; $i++) {
                if ($beforeLines[$i] -cne $afterLines[$i]) { $prefixMatches = $false; break }
            }
        }
        $fresh = if ($prefixMatches) { @($afterLines | Select-Object -Skip $beforeLines.Count) } else { $afterLines }
    }

    $probeLines = @($fresh | Select-String -SimpleMatch '[CompletionistRavenNativeBridgeProbe]' | ForEach-Object { $_.Line })
    if ($probeLines.Count -gt 0) {
        $probeLines | Set-Content -LiteralPath $extract -Encoding UTF8
    } else {
        'NO_COMPLETIONIST_RAVEN_NATIVE_BRIDGE_PROBE_LINES_FOUND' | Set-Content -LiteralPath $extract -Encoding UTF8
    }

    Restore-LocalState
    $mapAfterHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    @(
        "mapmenu_before_sha256=$mapBeforeHash"
        "mapmenu_after_restore_sha256=$mapAfterHash"
        "mapmenu_exact_restore=$($mapAfterHash -eq $mapBeforeHash)"
        "bridge_dll_restored=$($script:dllRestored.ToString().ToLowerInvariant())"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'restore-verification.txt') -Encoding UTF8
    if ($mapAfterHash -ne $mapBeforeHash) { throw 'mapmenu.lua restore hash mismatch.' }

    $ok = @($probeLines | Select-String -SimpleMatch 'BRIDGE_OK').Count -gt 0
    $failed = @($probeLines | Select-String -SimpleMatch 'BRIDGE_FAILED').Count -gt 0
    $result = if ($ok -and -not $failed) { 'RAVEN_NATIVE_LUA_BRIDGE_PROVEN' } else { 'RAVEN_NATIVE_LUA_BRIDGE_FAILED' }
    Publish-Capture $result
    $head = (& git rev-parse HEAD).Trim()
    Write-Host "$result"
    Write-Host "RAVEN_NATIVE_BRIDGE_PROBE_PUSHED $head" -ForegroundColor Green
    Write-Host "Evidence: $relativeDir"
    if (-not $ok -or $failed) { exit 1 }
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "RAVEN_NATIVE_BRIDGE_PROBE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Restore-LocalState } catch {}
    try { Publish-Capture 'RAVEN_NATIVE_LUA_BRIDGE_FAILED' } catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 1
}
finally {
    try { Restore-LocalState } catch {}
    foreach ($path in @($mapBackup, $dllBackup)) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
    }
    Stop-LocalTranscript
}
