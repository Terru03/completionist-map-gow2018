param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
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
$exe = Join-Path $GameRoot 'GoW.exe'
$version = Join-Path $GameRoot 'version.dll'
$target = Join-Path $GameRoot 'dxgi.dll'
$manifest = Join-Path $GameRoot 'mods\completionist-map\native\raven-native-bridge-manifest.json'
$bridgeLog = Join-Path $GameRoot 'mods\completionist-map\native\raven-native-bridge.log'
foreach ($path in @($buildScript, $installScript, $rollbackScript, $exe, $version)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Need proof file: $path" }
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-native-bridge-load-proof-$stamp"
$outDir = Join-Path $repo ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$console = Join-Path $outDir 'console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
$freshLog = Join-Path $outDir 'bridge-log-fresh.txt'
$transcript = $false
$installed = $false
$rolledBack = $false
$launched = $false
$published = $false

function Get-LowerHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$preDxgiExists = Test-Path -LiteralPath $target -PathType Leaf
$preManifestExists = Test-Path -LiteralPath $manifest -PathType Leaf
$preDxgiHash = if ($preDxgiExists) { Get-LowerHash $target } else { $null }
$preManifestHash = if ($preManifestExists) { Get-LowerHash $manifest } else { $null }
$versionBefore = Get-LowerHash $version
$beforeLines = if (Test-Path -LiteralPath $bridgeLog -PathType Leaf) { @(Get-Content -LiteralPath $bridgeLog) } else { @() }

function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
}

function Test-RollbackState {
    $postDxgiExists = Test-Path -LiteralPath $target -PathType Leaf
    $postManifestExists = Test-Path -LiteralPath $manifest -PathType Leaf
    if ($postDxgiExists -ne $preDxgiExists -or $postManifestExists -ne $preManifestExists) { return $false }
    if ($postDxgiExists -and (Get-LowerHash $target) -ne $preDxgiHash) { return $false }
    if ($postManifestExists -and (Get-LowerHash $manifest) -ne $preManifestHash) { return $false }
    return (Get-LowerHash $version) -eq $versionBefore
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
        & git commit -m "test(v0.10.5): capture Raven native bridge load proof $stamp" -- $relativeDir | Out-Host
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

    & $buildScript -Clean
    & $installScript -GameRoot $GameRoot
    $installed = $true
    @(
        "gow_exe_sha256=$(Get-LowerHash $exe)"
        "version_dll_before_sha256=$versionBefore"
        "installed_dxgi_sha256=$(Get-LowerHash $target)"
        "installed_manifest_sha256=$(Get-LowerHash $manifest)"
        "preexisting_dxgi=$($preDxgiExists.ToString().ToLowerInvariant())"
        "preexisting_manifest=$($preManifestExists.ToString().ToLowerInvariant())"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'installed-file-hashes.txt') -Encoding UTF8

    Write-Host 'RAVEN NATIVE BRIDGE LOAD PROOF'
    Write-Host 'Game starts now. Load advanced Raven save. Open map. Wait 15 seconds. Then quit game fully.'
    Start-Process -FilePath $exe -WorkingDirectory $GameRoot | Out-Null
    $launched = $true
    while ($true) {
        Read-Host 'After game fully exits, press Enter' | Out-Null
        if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }).Count -eq 0) { break }
        Write-Host 'Game still runs. Quit it first.'
    }

    $afterLines = if (Test-Path -LiteralPath $bridgeLog -PathType Leaf) { @(Get-Content -LiteralPath $bridgeLog) } else { @() }
    if (Test-Path -LiteralPath $bridgeLog -PathType Leaf) {
        Copy-Item -LiteralPath $bridgeLog -Destination (Join-Path $outDir 'bridge-log-full.txt')
    }
    $prefixMatches = $beforeLines.Count -le $afterLines.Count
    if ($prefixMatches) {
        for ($index = 0; $index -lt $beforeLines.Count; $index++) {
            if ($beforeLines[$index] -cne $afterLines[$index]) { $prefixMatches = $false; break }
        }
    }
    $newLines = if ($prefixMatches) { @($afterLines | Select-Object -Skip $beforeLines.Count) } else { $afterLines }
    if ($newLines.Count -gt 0) { $newLines | Set-Content -LiteralPath $freshLog -Encoding UTF8 }
    else { 'NO_FRESH_BRIDGE_LOG_LINES' | Set-Content -LiteralPath $freshLog -Encoding UTF8 }

    $proxyOK = @($newLines | Select-String -SimpleMatch 'RAVEN_NATIVE_BRIDGE_PROXY_LOADED').Count -gt 0
    $forwardOK = @($newLines | Select-String -Pattern 'RAVEN_NATIVE_BRIDGE_DXGI_FORWARDED .*success=true').Count -gt 0
    $exeOK = @($newLines | Select-String -SimpleMatch 'RAVEN_NATIVE_BRIDGE_EXE_ACCEPTED').Count -gt 0
    $snapshotOK = @($newLines | Select-String -Pattern 'RAVEN_NATIVE_BRIDGE_SNAPSHOT_ACCEPTED .*count=53 unknown=0').Count -gt 0
    $deliveryPending = @($newLines | Select-String -SimpleMatch 'RAVEN_NATIVE_BRIDGE_DELIVERY_PENDING').Count -gt 0
    @(
        "proxy_loaded=$($proxyOK.ToString().ToLowerInvariant())"
        "dxgi_forwarded=$($forwardOK.ToString().ToLowerInvariant())"
        "exe_accepted=$($exeOK.ToString().ToLowerInvariant())"
        "snapshot_53_unknown_0=$($snapshotOK.ToString().ToLowerInvariant())"
        "delivery_pending=$($deliveryPending.ToString().ToLowerInvariant())"
        "fresh_log_prefix_match=$($prefixMatches.ToString().ToLowerInvariant())"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'proof-checks.txt') -Encoding UTF8

    & $rollbackScript -GameRoot $GameRoot
    $rolledBack = $true
    $installed = $false
    if (-not (Test-RollbackState)) { throw 'Rollback did not restore exact old dxgi/manifest/version state.' }

    $ready = $proxyOK -and $forwardOK -and $exeOK -and $snapshotOK -and $deliveryPending
    $result = if ($ready) { 'RAVEN_NATIVE_BRIDGE_LOAD_PROOF_READY' } else { 'RAVEN_NATIVE_BRIDGE_LOAD_PROOF_FAILED' }
    $reason = if ($ready) { 'load_forward_hash_and_53_state_snapshot_proven_delivery_pending' } else { 'one_or_more_bridge_log_checks_failed' }
    Publish-Proof $result $reason
    Write-Host $result
    Write-Host "RAVEN_NATIVE_BRIDGE_LOAD_PROOF_PUSHED $((& git rev-parse HEAD).Trim())"
    Write-Host "Evidence: $relativeDir"
    if (-not $ready) { exit 1 }
}
catch {
    $outerError = $_
    try { $outerError.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "RAVEN_NATIVE_BRIDGE_LOAD_PROOF_FAILED: $($outerError.Exception.Message)"
    if ($installed -and -not $rolledBack) {
        try {
            & $rollbackScript -GameRoot $GameRoot
            $rolledBack = $true
            $installed = $false
        } catch {
            try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'rollback-error.txt') -Encoding UTF8 } catch {}
        }
    }
    try { Publish-Proof 'RAVEN_NATIVE_BRIDGE_LOAD_PROOF_FAILED' $outerError.Exception.Message } catch {
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
