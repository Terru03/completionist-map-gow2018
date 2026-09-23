param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$EvidenceRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branchWanted = 'codex/collectible-legendary-chests'
$sourceHash = [ordered]@{
    'exec/dc/pc_le/mapmaster.dcb' = 'aec578e773898a1e60d5ccedd0df08e35b12ab54e4d26f4cd90740948430c2a0'
    'exec/dc/pc_le/mapcoords.dcb' = '5d0b7591032d7b56581a0d77946c3fad4f0cbc1b9d245f3578407177c40bbe7d'
    'exec/dc/pc_le/wad_r_ui.dcb' = '21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a'
    'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua' = '9cd37988f44cdb906415737bff4ff8eec62fbda9baf46a5359ebed6aa6466c08'
    'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua' = 'c5370981988a8e4c7c01f2bee68946a2ef1aa70d6b6f391a04e165f68ae610a8'
}
$exeHashWanted = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
$bridgeDll = Join-Path $repoRoot 'archive/legendary-live-test/raven-bridge-base/Release/dxgi.dll'
$bridgeBuild = Join-Path $repoRoot 'archive/legendary-live-test/raven-bridge-base/bridge-build-manifest.json'
$bridgeShaWanted = 'bfa20652f3a12d1d72930417f80defcba520eb6c5989fdf1a94d36f462f31851'
$engine = Join-Path $repoRoot 'tools/v0.10.4/nornir-runtime-candidate3.ps1'
$engineShaWanted = '83f11f8e3a5b6e56ad5d06ba22baa779f91c986ace42ab3017de2b2231d7057a'
$builder = Join-Path $repoRoot 'tools/v0.10.5/build-legendary-live-test-marker.py'
$candidate = Join-Path $repoRoot 'build/v0.10.5-legendary-live-test/candidate/game-root'
$proofPath = Join-Path $repoRoot 'build/v0.10.5-legendary-live-test/candidate/build-report.json'
$state = Join-Path $repoRoot 'build/v0.10.5-legendary-live-test/transaction'
$active = Join-Path $state 'active.json'

function Sha([string]$path) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Need file: $path" }
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function CanonicalScriptSha([string]$path) {
    $text = [IO.File]::ReadAllText($path).Replace("`r`n", "`n").Replace("`r", "`n")
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($text))).ToLowerInvariant()
}
function Assert-Closed {
    if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
        throw 'Close God of War first.'
    }
}
function Assert-Repo {
    $current = (& git -C $repoRoot branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $current -ne $branchWanted) { throw "Wrong branch: $current" }
    $changes = @(& git -C $repoRoot status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0 -or $changes.Count -ne 0) { throw "Working tree dirty: $($changes -join ', ')" }
}
function Assert-Source([switch]$BridgeInstalled) {
    Assert-Closed
    if ((Sha (Join-Path $GameRoot 'GoW.exe')) -ne $exeHashWanted) { throw 'Unsupported GoW.exe hash.' }
    foreach ($relative in $sourceHash.Keys) {
        $actual = Sha (Join-Path $GameRoot $relative)
        if ($actual -ne $sourceHash[$relative]) { throw "Unsupported installed file: $relative sha256=$actual" }
    }
    if ($BridgeInstalled) {
        if ((Sha (Join-Path $GameRoot 'dxgi.dll')) -ne $bridgeShaWanted) { throw 'Installed Raven bridge hash changed.' }
        $installedBridge = Get-Content -Raw -LiteralPath (Join-Path $GameRoot 'mods/completionist-map/native/raven-native-bridge-manifest.json') | ConvertFrom-Json
        if ($installedBridge.installed_sha256 -ne $bridgeShaWanted) { throw 'Installed Raven bridge manifest changed.' }
    } else {
        foreach ($relative in @('dxgi.dll','mods/completionist-map/native/raven-native-bridge-manifest.json')) {
            if (Test-Path -LiteralPath (Join-Path $GameRoot $relative)) { throw "Existing native bridge needs review: $relative" }
        }
    }
}

if ([string]::IsNullOrWhiteSpace($EvidenceRoot)) { throw 'EvidenceRoot required.' }
$evidence = [IO.Path]::GetFullPath($EvidenceRoot)
if (-not (Test-Path -LiteralPath $evidence -PathType Container)) { throw "EvidenceRoot missing: $evidence" }
Assert-Repo
Assert-Source
if ((CanonicalScriptSha $engine) -ne $engineShaWanted) { throw 'Proven Raven transaction engine changed.' }
if ((Sha $bridgeDll) -ne $bridgeShaWanted) { throw 'Proven Raven authority bridge changed.' }
$bridgeManifest = Get-Content -Raw -LiteralPath $bridgeBuild | ConvertFrom-Json
if ($bridgeManifest.dll_sha256 -ne $bridgeShaWanted -or $bridgeManifest.supported_exe_sha256 -ne $exeHashWanted) {
    throw 'Raven authority bridge build record changed.'
}
if (Test-Path -LiteralPath $active -PathType Leaf) { throw "Prior Legendary transaction needs review: $active" }

& python $builder --game-root $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Legendary candidate build failed.' }
& python $builder --game-root $GameRoot --check
if ($LASTEXITCODE -ne 0) { throw 'Legendary candidate rebuild check failed.' }
$proof = Get-Content -Raw -LiteralPath $proofPath | ConvertFrom-Json
if ($proof.result -ne 'ONE_FORCED_LEGENDARY_MARKER_READY_FOR_MANUAL_MAP_TEST' -or
    $proof.target.catalogue_id -ne 'legendary_chest_529343984fc313504ac20da874d05c01') {
    throw 'Legendary candidate proof mismatch.'
}

$fileMap = [ordered]@{}
$candidateShas = [ordered]@{}
foreach ($relative in $sourceHash.Keys) {
    $fileMap[$relative] = $relative
    $candidateShas[$relative] = [string]$proof.candidate_files.$relative.sha256
    if ((Sha (Join-Path $candidate $relative)) -ne $candidateShas[$relative]) { throw "Candidate hash mismatch: $relative" }
}

Assert-Repo
Assert-Source
$head = (& git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') { throw 'Bad Git HEAD.' }
$loaderLog = Join-Path $GameRoot 'mods/loader_log.txt'
$logStart = [ordered]@{ path = $loaderLog; exists = (Test-Path -LiteralPath $loaderLog -PathType Leaf); bytes = $null; sha256 = $null }
if ($logStart.exists) {
    $logStart.bytes = (Get-Item -LiteralPath $loaderLog).Length
    $logStart.sha256 = Sha $loaderLog
}
$logStart | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'loader-log-before.json') -Encoding UTF8
Copy-Item -LiteralPath $proofPath -Destination (Join-Path $evidence 'candidate-build-report.json')

# Source stays in ignored build tree. Proven transaction engine backs up all five files first.
if ((CanonicalScriptSha $engine) -ne $engineShaWanted) { throw 'Transaction engine changed before load.' }
. $engine -LibraryOnly
$repo = $repoRoot
$expectedBranch = $branchWanted
Assert-PathTopology -Game $GameRoot -Candidate $candidate -State $state
$preWrite = {
    Assert-Repo
    Assert-Source -BridgeInstalled
    if ((& git -C $repoRoot rev-parse HEAD).Trim() -ne $head) { throw 'HEAD changed before game write.' }
}
$writeGuard = { Assert-Closed }
$bridgeInstalled = $false
$mapInstalled = $false
try {
    Assert-Repo
    Assert-Source
    & (Join-Path $repoRoot 'tools/v0.10.5/install-raven-authority-bridge.ps1') -GameRoot $GameRoot -BridgeDll $bridgeDll -BuildManifest $bridgeBuild
    if (-not $?) { throw 'Raven authority bridge install failed.' }
    $bridgeInstalled = $true
    $manifest = Invoke-TransactionalInstall -Game $GameRoot -Candidate $candidate -State $state -Active $active `
        -FileMap $fileMap -CandidateShas $candidateShas -CandidateLabel 'legendary-live-test-raven-base' `
        -RepoBranch $branchWanted -RepoHead $head -ProofPath $proofPath -PreWriteValidation $preWrite -WriteGuard $writeGuard
    $mapInstalled = $true
    $manifest | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $evidence 'install-transaction.json') -Encoding UTF8
    $backupRoot = Join-Path ([string]$manifest.transaction_root) 'backup/game-root'
    if (-not (Test-Path -LiteralPath $backupRoot -PathType Container)) { throw 'Transaction backup missing.' }
    Copy-Item -LiteralPath $backupRoot -Destination (Join-Path $evidence 'backup-game-root') -Recurse
    Copy-Item -LiteralPath (Join-Path $GameRoot 'mods/completionist-map/native/raven-native-bridge-manifest.json') `
        -Destination (Join-Path $evidence 'bridge-install-manifest.json')
    $result = [ordered]@{
        result = 'PREPARED_NO_GAME_LAUNCH'
        branch = $branchWanted
        head = $head
        target = $proof.target
        map_point_delivered_float16 = $proof.map_point_delivered_float16
        raven_markers_installed = 53
        diagnostic_markers_installed = 1
        bridge_sha256 = Sha (Join-Path $GameRoot 'dxgi.dll')
        bridge_before = 'absent'
        bridge_manifest_relative = 'mods/completionist-map/native/raven-native-bridge-manifest.json'
        transaction_id = $manifest.transaction_id
        transaction_root = $manifest.transaction_root
        modified_files = @($manifest.entries | ForEach-Object { [ordered]@{ relative=$_.relative; before_sha256=$_.before_sha256; after_sha256=$_.candidate_sha256; backup_relative=$_.backup_relative } })
        loader_log_before = $logStart
        loader_log_event_prefix = '[CompletionistMap v0.10.5]'
        restore = 'Run tools/v0.10.5/restore-legendary-live-test-marker.ps1 with God of War closed.'
    }
    $result | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $evidence 'prepare-result.json') -Encoding UTF8
    Write-Host "LEGENDARY_LIVE_TEST_PREPARED transaction=$($manifest.transaction_id) evidence=$evidence"
}
catch {
    $failure = $_.Exception.Message
    if (-not $mapInstalled -and (Test-Path -LiteralPath $active -PathType Leaf)) {
        $lastState = (Get-Content -Raw -LiteralPath $active | ConvertFrom-Json).status
        if ($lastState -eq 'rollback-failed-after-install-failure') {
            throw "Map install and rollback failed: $failure. Keep bridge in place. Do not launch game."
        }
    }
    if ($mapInstalled) {
        try {
            Restore-State -Manifest $manifest -Game $GameRoot -Candidate $candidate -State $state -Active $active `
                -ProofPath $proofPath -FileMap $fileMap -CandidateShas $candidateShas `
                -CandidateLabel 'legendary-live-test-raven-base' -RepoBranch $branchWanted -CheckInstalled $true -Force $false -WriteGuard $writeGuard
        }
        catch { throw "Install failed: $failure. Map rollback failed: $($_.Exception.Message). Do not launch game." }
    }
    if ($bridgeInstalled) {
        try {
            & (Join-Path $repoRoot 'tools/v0.10.5/rollback-raven-authority-bridge.ps1') -GameRoot $GameRoot
            if (-not $?) { throw 'Bridge rollback command failed.' }
        }
        catch { throw "Install failed: $failure. Bridge rollback failed: $($_.Exception.Message). Do not launch game." }
    }
    throw $failure
}
