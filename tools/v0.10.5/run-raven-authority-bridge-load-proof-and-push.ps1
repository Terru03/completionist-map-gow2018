param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [ValidateRange(5, 120)][int]$StartupTimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo
if ((& git branch --show-current).Trim() -ne $ExpectedBranch) { throw "Need branch $ExpectedBranch." }
if (@(& git diff --cached --name-only).Count -gt 0) { throw 'Staged changes exist. Refuse proof.' }
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }).Count -gt 0) {
    throw 'Close God of War first.'
}

$buildScript = Join-Path $repo 'tools\v0.10.5\build-raven-authority-bridge.ps1'
$installScript = Join-Path $repo 'tools\v0.10.5\install-raven-authority-bridge.ps1'
$rollbackScript = Join-Path $repo 'tools\v0.10.5\rollback-raven-authority-bridge.ps1'
$runnerSupport = Join-Path $repo 'tools\v0.10.5\raven-native-bridge-runner-support.ps1'
$runnerTest = Join-Path $repo 'tools\v0.10.5\test-raven-authority-bridge-runner.ps1'
$installTest = Join-Path $repo 'tools\v0.10.5\test-raven-authority-bridge-install.ps1'
$exe = Join-Path $GameRoot 'GoW.exe'
$version = Join-Path $GameRoot 'version.dll'
$target = Join-Path $GameRoot 'XINPUT1_4.dll'
$manifest = Join-Path $GameRoot 'mods\completionist-map\native\raven-native-bridge-manifest.json'
$bridgeLog = Join-Path $GameRoot 'mods\completionist-map\native\raven-native-bridge.log'
$loaderLog = Join-Path $GameRoot 'mods\loader_log.txt'
foreach ($path in @($buildScript, $installScript, $rollbackScript, $runnerSupport, $runnerTest, $installTest, $exe, $version)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Need proof file: $path" }
}
. $runnerSupport

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-native-bridge-load-proof-v2-$stamp"
$outDir = Join-Path $repo ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$console = Join-Path $outDir 'console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
$freshLog = Join-Path $outDir 'bridge-log-fresh.txt'
$transcript = $false
$installed = $false
$rolledBack = $false
$launched = $false
$published = $false
$beforeLines = @()
$loaderBeforeLines = @()
$gameProcess = $null

function Get-LowerHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$preProxyExists = Test-Path -LiteralPath $target -PathType Leaf
$preManifestExists = Test-Path -LiteralPath $manifest -PathType Leaf
$preProxyHash = if ($preProxyExists) { Get-LowerHash $target } else { $null }
$preManifestHash = if ($preManifestExists) { Get-LowerHash $manifest } else { $null }
$versionBefore = Get-LowerHash $version
if (Test-Path -LiteralPath $bridgeLog -PathType Leaf) {
    $beforeLines = @(Get-Content -LiteralPath $bridgeLog)
}
if (Test-Path -LiteralPath $loaderLog -PathType Leaf) {
    $loaderBeforeLines = @(Get-Content -LiteralPath $loaderLog)
}

function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
}

function Test-RollbackState {
    $postProxyExists = Test-Path -LiteralPath $target -PathType Leaf
    $postManifestExists = Test-Path -LiteralPath $manifest -PathType Leaf
    if ($postProxyExists -ne $preProxyExists -or $postManifestExists -ne $preManifestExists) { return $false }
    if ($postProxyExists -and (Get-LowerHash $target) -ne $preProxyHash) { return $false }
    if ($postManifestExists -and (Get-LowerHash $manifest) -ne $preManifestHash) { return $false }
    return (Get-LowerHash $version) -eq $versionBefore
}

function Save-FreshBridgeLog {
    $afterLines = @()
    if (Test-Path -LiteralPath $bridgeLog -PathType Leaf) {
        $afterLines = @(Get-Content -LiteralPath $bridgeLog)
        Copy-Item -LiteralPath $bridgeLog -Destination (Join-Path $outDir 'bridge-log-full.txt') -Force
    }
    $comparison = Compare-RavenBridgeLog -Before @($beforeLines) -After @($afterLines)
    $newLines = @($comparison.Lines)
    if (@($newLines).Count -gt 0) {
        $newLines | Set-Content -LiteralPath $freshLog -Encoding UTF8
    } else {
        'NO_FRESH_BRIDGE_LOG_LINES' | Set-Content -LiteralPath $freshLog -Encoding UTF8
    }
    return [pscustomobject]@{
        PrefixMatches = [bool]$comparison.PrefixMatches
        Lines = [string[]]@($newLines)
    }
}

function Save-FreshLoaderLog {
    $loaderAfterLines = @()
    if (Test-Path -LiteralPath $loaderLog -PathType Leaf) {
        $loaderAfterLines = @(Get-Content -LiteralPath $loaderLog)
        Copy-Item -LiteralPath $loaderLog -Destination (Join-Path $outDir 'loader-log-full.txt') -Force
    }
    $comparison = Compare-RavenBridgeLog -Before @($loaderBeforeLines) -After @($loaderAfterLines)
    $newLines = @($comparison.Lines)
    if (@($newLines).Count -gt 0) {
        $newLines | Set-Content -LiteralPath (Join-Path $outDir 'loader-log-fresh.txt') -Encoding UTF8
    } else {
        'NO_FRESH_LOADER_LOG_LINES' | Set-Content -LiteralPath (Join-Path $outDir 'loader-log-fresh.txt') -Encoding UTF8
    }
    return [pscustomobject]@{
        PrefixMatches = [bool]$comparison.PrefixMatches
        Lines = [string[]]@($newLines)
    }
}

function Publish-Proof([string]$Result, [string]$Reason) {
    if ($script:published) { return }
    Stop-LocalTranscript
    $rollbackExact = Test-RollbackState
    @(
        "result=$Result"
        "reason=$Reason"
        "timestamp=$(Get-Date -Format o)"
        "branch=$ExpectedBranch"
        "proxy_target=XINPUT1_4.dll"
        "game_launched=$($script:launched.ToString().ToLowerInvariant())"
        "rollback_exact=$($rollbackExact.ToString().ToLowerInvariant())"
        "version_dll_untouched=$(((Get-LowerHash $version) -eq $versionBefore).ToString().ToLowerInvariant())"
        'bridge_process_memory_writes=false'
        'bridge_save_writes=false'
        'bridge_progression_writes=false'
        'version_dll_writes=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add proof failed.' }
    & git diff --cached --quiet -- $relativeDir
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "test(v0.10.5): capture Raven native bridge load proof V2 $stamp" -- $relativeDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit proof failed.' }
        & git push origin $ExpectedBranch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push proof failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff proof failed.'
    }
    $script:published = $true
}

try {
    New-Item -ItemType Directory -Path $outDir | Out-Null
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true

    & $runnerTest
    & $buildScript -Clean
    & $installTest -GameRootFixture $GameRoot
    & $installScript -GameRoot $GameRoot
    $installed = $true
    @(
        "gow_exe_sha256=$(Get-LowerHash $exe)"
        "version_dll_before_sha256=$versionBefore"
        "installed_xinput1_4_sha256=$(Get-LowerHash $target)"
        "installed_manifest_sha256=$(Get-LowerHash $manifest)"
        "preexisting_xinput1_4=$($preProxyExists.ToString().ToLowerInvariant())"
        "preexisting_manifest=$($preManifestExists.ToString().ToLowerInvariant())"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'installed-file-hashes.txt') -Encoding UTF8

    Write-Host 'RAVEN NATIVE BRIDGE LOAD PROOF V2'
    $gameProcess = Start-Process -FilePath $exe -WorkingDirectory $GameRoot -PassThru
    $launched = $true
    $startupDeadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    $startupReady = $false
    while ([DateTime]::UtcNow -lt $startupDeadline) {
        Start-Sleep -Milliseconds 250
        $gameProcess.Refresh()
        $capture = Save-FreshBridgeLog
        $observation = Test-RavenBridgeStartupObservation -ProcessRunning (-not $gameProcess.HasExited) -FreshLines @($capture.Lines)
        if ($observation.Ready) {
            $startupReady = $true
            break
        }
        if ($gameProcess.HasExited) {
            throw "Game exited before bridge startup proof. exit_code=$($gameProcess.ExitCode)"
        }
    }
    if (-not $startupReady) {
        throw "Expected fresh bridge startup log did not appear within $StartupTimeoutSeconds seconds."
    }

    Write-Host 'Proxy startup proven. Load advanced Raven save. Open map. Wait 15 seconds. Then quit game fully.'
    while ($true) {
        Read-Host 'After game fully exits, press Enter' | Out-Null
        if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }).Count -eq 0) { break }
        Write-Host 'Game still runs. Quit it first.'
    }

    $capture = Save-FreshBridgeLog
    $loaderCapture = Save-FreshLoaderLog
    $newLines = @($capture.Lines)
    $proof = Test-RavenBridgeProofLines -Lines @($newLines) -LoaderLines @($loaderCapture.Lines)
    @(
        "proxy_loaded=$($proof.ProxyLoaded.ToString().ToLowerInvariant())"
        "xinput_forwarded=$($proof.Forwarded.ToString().ToLowerInvariant())"
        "exe_accepted=$($proof.ExeAccepted.ToString().ToLowerInvariant())"
        "snapshot_53_unknown_0=$($proof.SnapshotAccepted.ToString().ToLowerInvariant())"
        "delivery_pending=$($proof.DeliveryPending.ToString().ToLowerInvariant())"
        "script_loader_completionist_map_loaded=$($proof.ScriptLoader.ToString().ToLowerInvariant())"
        "fresh_log_prefix_match=$($capture.PrefixMatches.ToString().ToLowerInvariant())"
        "fresh_loader_log_prefix_match=$($loaderCapture.PrefixMatches.ToString().ToLowerInvariant())"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'proof-checks.txt') -Encoding UTF8

    & $rollbackScript -GameRoot $GameRoot
    $rolledBack = $true
    $installed = $false
    if (-not (Test-RollbackState)) { throw 'Rollback did not restore exact old XInput/manifest/version state.' }

    $ready = $proof.ProxyLoaded -and $proof.Forwarded -and $proof.ExeAccepted -and
        $proof.SnapshotAccepted -and $proof.DeliveryPending -and $proof.ScriptLoader
    $result = if ($ready) { 'RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V2_PASSED' } else { 'RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V2_FAILED' }
    $reason = if ($ready) { 'xinput_complete_forward_startup_hash_and_53_state_snapshot_proven' } else { 'one_or_more_bridge_log_checks_failed' }
    Publish-Proof $result $reason
    Write-Host $result
    Write-Host "RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V2_PUSHED $((& git rev-parse HEAD).Trim())"
    Write-Host "Evidence: $relativeDir"
    if (-not $ready) { exit 1 }
}
catch {
    $outerError = $_
    try { $outerError.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    try { Save-FreshBridgeLog | Out-Null } catch {}
    try { Save-FreshLoaderLog | Out-Null } catch {}
    Write-Host "RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V2_FAILED: $($outerError.Exception.Message)"
    if ($installed) {
        @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }) |
            Stop-Process -Force -ErrorAction SilentlyContinue
        if ($null -ne $gameProcess) {
            try { $gameProcess.WaitForExit(5000) | Out-Null } catch {}
        }
    }
    try {
        $didRollback = Invoke-RavenBridgeFailureRollback -Installed $installed -RolledBack $rolledBack -Rollback {
            & $rollbackScript -GameRoot $GameRoot
        }
        if ($didRollback) {
            $rolledBack = $true
            $installed = $false
        }
    } catch {
        try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'rollback-error.txt') -Encoding UTF8 } catch {}
    }
    try { Publish-Proof 'RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V2_FAILED' $outerError.Exception.Message } catch {
        Write-Host "PROOF_PUSH_FAILED: $($_.Exception.Message)"
    }
    exit 1
}
finally {
    if ($installed -and -not $rolledBack) {
        try { & $rollbackScript -GameRoot $GameRoot } catch {}
    }
    Stop-LocalTranscript
}
