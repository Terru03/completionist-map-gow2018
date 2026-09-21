param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [ValidateRange(30, 180)][int]$StartupTimeoutSeconds = 90,
    [ValidateRange(20, 90)][int]$MainMenuSettleSeconds = 40
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

$game = [IO.Path]::GetFullPath($GameRoot)
$exe = Join-Path $game 'GoW.exe'
$version = Join-Path $game 'version.dll'
$target = Join-Path $game 'dxgi.dll'
$manifest = Join-Path $game 'mods\completionist-map\native\raven-native-bridge-manifest.json'
$bridgeLog = Join-Path $game 'mods\completionist-map\native\raven-native-bridge.log'
$loaderLog = Join-Path $game 'mods\loader_log.txt'

foreach ($required in @($buildScript, $installScript, $rollbackScript, $runnerSupport, $runnerTest, $installTest, $exe, $version)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Need proof file: $required" }
}
. $runnerSupport

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-native-bridge-load-proof-v3-$stamp"
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
$baselineGamePids = @()
$startupGamePids = @()
$bootstrapExitCode = $null

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

function Stop-GoWProcesses {
    @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }) |
        Stop-Process -Force -ErrorAction SilentlyContinue
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }).Count -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw 'GoW process remained alive after forced shutdown request.'
}

function Test-RollbackState {
    $postProxyExists = Test-Path -LiteralPath $target -PathType Leaf
    $postManifestExists = Test-Path -LiteralPath $manifest -PathType Leaf

    if ($postProxyExists -ne $preProxyExists -or $postManifestExists -ne $preManifestExists) {
        return $false
    }
    if ($postProxyExists -and (Get-LowerHash $target) -ne $preProxyHash) {
        return $false
    }
    if ($postManifestExists -and (Get-LowerHash $manifest) -ne $preManifestHash) {
        return $false
    }
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
    $afterLines = @()
    if (Test-Path -LiteralPath $loaderLog -PathType Leaf) {
        $afterLines = @(Get-Content -LiteralPath $loaderLog)
        Copy-Item -LiteralPath $loaderLog -Destination (Join-Path $outDir 'loader-log-full.txt') -Force
    }
    $comparison = Compare-RavenBridgeLog -Before @($loaderBeforeLines) -After @($afterLines)
    $newLines = @($comparison.Lines)
    $path = Join-Path $outDir 'loader-log-fresh.txt'
    if (@($newLines).Count -gt 0) {
        $newLines | Set-Content -LiteralPath $path -Encoding UTF8
    } else {
        'NO_FRESH_LOADER_LOG_LINES' | Set-Content -LiteralPath $path -Encoding UTF8
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
        'proxy_target=dxgi.dll'
        'proxy_contract=system32-dxgi-v1'
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
        & git commit -m "test(v0.10.5): capture Raven native DXGI load proof V3 $stamp" -- $relativeDir | Out-Host
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

    Write-Host 'RAVEN NATIVE DXGI BRIDGE LOAD PROOF V3 - OFFLINE GATES'
    & $runnerTest
    & $buildScript -Clean
    & $installTest -GameRootFixture $game

    Write-Host 'Offline gates passed. Installing owned DXGI proxy for reversible live proof.'
    & $installScript -GameRoot $game
    $installed = $true

    @(
        "gow_exe_sha256=$(Get-LowerHash $exe)"
        "version_dll_before_sha256=$versionBefore"
        "installed_dxgi_sha256=$(Get-LowerHash $target)"
        "installed_manifest_sha256=$(Get-LowerHash $manifest)"
        "preexisting_dxgi=$($preProxyExists.ToString().ToLowerInvariant())"
        "preexisting_manifest=$($preManifestExists.ToString().ToLowerInvariant())"
        'proxy_contract=system32-dxgi-v1'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'installed-file-hashes.txt') -Encoding UTF8

    Write-Host 'RAVEN NATIVE DXGI BRIDGE LOAD PROOF V3'
    $baselineGamePids = @(Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') } |
        Select-Object -ExpandProperty Id)

    $gameProcess = Start-Process -FilePath $exe -WorkingDirectory $game -PassThru
    $launched = $true
    $startupDeadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    $startupReady = $false

    while ([DateTime]::UtcNow -lt $startupDeadline) {
        Start-Sleep -Milliseconds 250

        if ($null -ne $gameProcess -and $null -eq $bootstrapExitCode) {
            try {
                $gameProcess.Refresh()
                if ($gameProcess.HasExited) {
                    $bootstrapExitCode = $gameProcess.ExitCode
                }
            } catch {}
        }

        $liveGameProcesses = @(Get-Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ProcessName -in @('GoW', 'GodOfWar') -and
                $baselineGamePids -notcontains $_.Id
            })

        $capture = Save-FreshBridgeLog
        $observation = Test-RavenBridgeStartupObservation -ProcessRunning (@($liveGameProcesses).Count -gt 0) -FreshLines @($capture.Lines)

        if ($observation.Ready) {
            $startupGamePids = @($liveGameProcesses | Select-Object -ExpandProperty Id)
            $startupReady = $true
            break
        }
    }

    if (-not $startupReady) {
        $bootstrapExitText = if ($null -eq $bootstrapExitCode) { 'unknown_or_running' } else { [string]$bootstrapExitCode }
        throw "Fresh DXGI bridge startup evidence plus a live GoW process did not appear within $StartupTimeoutSeconds seconds. bootstrap_exit_code=$bootstrapExitText"
    }

    @(
        "bootstrap_pid=$($gameProcess.Id)"
        "bootstrap_exited=$((($null -ne $bootstrapExitCode)).ToString().ToLowerInvariant())"
        "bootstrap_exit_code=$(if ($null -eq $bootstrapExitCode) { 'n/a' } else { $bootstrapExitCode })"
        "startup_game_pids=$($startupGamePids -join ',')"
        'steam_handoff_tolerated=true'
        "main_menu_settle_seconds=$MainMenuSettleSeconds"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'startup-processes.txt') -Encoding UTF8

    Write-Host "DXGI proxy startup proven. Waiting $MainMenuSettleSeconds seconds for the normal main-menu startup window..."
    Start-Sleep -Seconds $MainMenuSettleSeconds

    if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }).Count -eq 0) {
        throw 'GoW exited during the main-menu settle window.'
    }

    $startupCapture = Save-FreshBridgeLog
    $startupProof = Test-RavenBridgeProofLines -Lines @($startupCapture.Lines)
    if (-not $startupProof.ProxyLoaded -or -not $startupProof.Forwarded -or -not $startupProof.ExeAccepted) {
        throw 'DXGI proxy loaded but startup forwarding/executable acceptance proof is incomplete.'
    }

    Write-Host 'DXGI bridge startup is healthy.'
    Write-Host 'Load the advanced Raven save, open the map, wait at least 15 seconds, then quit GoW fully.'

    while ($true) {
        Read-Host 'After GoW fully exits, press Enter' | Out-Null
        if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }).Count -eq 0) {
            break
        }
        Write-Host 'GoW is still running. Quit it fully before continuing.'
    }

    $capture = Save-FreshBridgeLog
    $loaderCapture = Save-FreshLoaderLog
    $proof = Test-RavenBridgeProofLines -Lines @($capture.Lines) -LoaderLines @($loaderCapture.Lines)

    @(
        "proxy_loaded=$($proof.ProxyLoaded.ToString().ToLowerInvariant())"
        "dxgi_forwarded=$($proof.Forwarded.ToString().ToLowerInvariant())"
        "exe_accepted=$($proof.ExeAccepted.ToString().ToLowerInvariant())"
        "snapshot_53_unknown_0=$($proof.SnapshotAccepted.ToString().ToLowerInvariant())"
        "delivery_pending=$($proof.DeliveryPending.ToString().ToLowerInvariant())"
        "script_loader_completionist_map_loaded=$($proof.ScriptLoader.ToString().ToLowerInvariant())"
        "fresh_log_prefix_match=$($capture.PrefixMatches.ToString().ToLowerInvariant())"
        "fresh_loader_log_prefix_match=$($loaderCapture.PrefixMatches.ToString().ToLowerInvariant())"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'proof-checks.txt') -Encoding UTF8

    & $rollbackScript -GameRoot $game
    $rolledBack = $true
    $installed = $false

    if (-not (Test-RollbackState)) {
        throw 'Rollback did not restore exact pre-run DXGI/manifest/version state.'
    }

    $ready = $proof.ProxyLoaded -and $proof.Forwarded -and $proof.ExeAccepted -and $proof.SnapshotAccepted -and $proof.DeliveryPending -and $proof.ScriptLoader
    $result = if ($ready) { 'RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V3_PASSED' } else { 'RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V3_FAILED' }
    $reason = if ($ready) { 'dxgi_complete_forward_startup_hash_53_state_snapshot_and_script_loader_proven' } else { 'one_or_more_dxgi_bridge_log_checks_failed' }

    Publish-Proof $result $reason
    Write-Host $result
    Write-Host "RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V3_PUSHED $((& git rev-parse HEAD).Trim())"
    Write-Host "Evidence: $relativeDir"

    if (-not $ready) { exit 1 }
}
catch {
    $outerError = $_
    try {
        $outerError.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8
    } catch {}
    try { Save-FreshBridgeLog | Out-Null } catch {}
    try { Save-FreshLoaderLog | Out-Null } catch {}

    Write-Host "RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V3_FAILED: $($outerError.Exception.Message)"

    if ($installed) {
        try { Stop-GoWProcesses } catch {
            try {
                $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'game-stop-error.txt') -Encoding UTF8
            } catch {}
        }
    }

    try {
        $didRollback = Invoke-RavenBridgeFailureRollback -Installed $installed -RolledBack $rolledBack -Rollback {
            & $rollbackScript -GameRoot $game
        }
        if ($didRollback) {
            $rolledBack = $true
            $installed = $false
        }
    } catch {
        try {
            $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'rollback-error.txt') -Encoding UTF8
        } catch {}
    }

    try {
        Publish-Proof 'RAVEN_NATIVE_BRIDGE_LOAD_PROOF_V3_FAILED' $outerError.Exception.Message
    } catch {
        Write-Host "PROOF_PUSH_FAILED: $($_.Exception.Message)"
    }
    exit 1
}
finally {
    if ($installed -and -not $rolledBack) {
        try {
            Stop-GoWProcesses
            & $rollbackScript -GameRoot $game
        } catch {}
    }
    Stop-LocalTranscript
}
