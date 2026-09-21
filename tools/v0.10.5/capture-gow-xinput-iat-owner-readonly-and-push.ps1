param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [ValidateRange(30,180)][int]$StartupTimeoutSeconds = 90,
    [ValidateRange(20,90)][int]$SettleSeconds = 40
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo
if ((& git branch --show-current).Trim() -ne $ExpectedBranch) { throw "Need branch $ExpectedBranch." }
if (@(& git diff --cached --name-only).Count -gt 0) { throw 'Staged changes exist. Refuse capture.' }
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War first.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$exe = Join-Path $game 'GoW.exe'
$version = Join-Path $game 'version.dll'
$xinputLocal = Join-Path $game 'XINPUT1_4.dll'
$manifest = Join-Path $game 'mods\completionist-map\native\raven-native-bridge-manifest.json'
$buildScript = Join-Path $repo 'tools\v0.10.5\build-raven-authority-bridge.ps1'
foreach ($p in @($exe,$version,$buildScript)) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Required file missing: $p" }
}
if (Test-Path -LiteralPath $xinputLocal -PathType Leaf) {
    throw "Game-root XINPUT1_4.dll exists. Recover the native bridge first: $xinputLocal"
}
if (Test-Path -LiteralPath $manifest -PathType Leaf) {
    throw "Raven native bridge manifest exists. Recover the native bridge first: $manifest"
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/gow-xinput-iat-owner-$stamp"
$outDir = Join-Path $repo ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$probeLog = Join-Path $outDir 'iat-probe.txt'
$resultFile = Join-Path $outDir 'result.txt'
$knownDllLog = Join-Path $outDir 'known-dlls.txt'
$tasklistLog = Join-Path $outDir 'tasklist-xinput.txt'
$transcript = $false
$bootstrap = $null
$target = $null

function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
}

function Write-KnownDllEvidence {
    $lines = @()
    foreach ($registryPath in @(
        'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Session Manager\KnownDLLs',
        'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Session Manager\KnownDLLs32'
    )) {
        try {
            $key = Get-Item -LiteralPath $registryPath -ErrorAction Stop
            $matches = @()
            foreach ($name in @($key.GetValueNames())) {
                $value = [string]$key.GetValue($name)
                if ($value -match '(?i)^xinput1_4\.dll$') {
                    $matches += "$name=$value"
                }
            }
            if (@($matches).Count -eq 0) {
                $lines += "$registryPath : XINPUT1_4_NOT_LISTED"
            } else {
                foreach ($match in $matches) {
                    $lines += "$registryPath : $match"
                }
            }
        } catch {
            $lines += "$registryPath : QUERY_FAILED $($_.Exception.Message)"
        }
    }
    $lines | Set-Content -LiteralPath $knownDllLog -Encoding UTF8
}

function Publish-Capture {
    Stop-LocalTranscript
    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add capture failed.' }
    & git diff --cached --quiet -- $relativeDir
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "research(v0.10.5): capture live GoW XInput IAT owner $stamp" -- $relativeDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit capture failed.' }
        & git push origin $ExpectedBranch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push capture failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff capture failed.'
    }
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true

    Write-Host 'GOW XINPUT IAT OWNER CAPTURE - READ ONLY'
    Write-Host 'No proxy is installed. No save load is required.'
    Write-Host 'Building and self-testing the native targeted probe...'

    & $buildScript -Clean
    if ($LASTEXITCODE -ne 0) { throw 'Native bridge/probe build failed.' }

    $probe = Join-Path $repo 'build\raven-authority-bridge\Release\raven_bridge_import_probe.exe'
    if (-not (Test-Path -LiteralPath $probe -PathType Leaf)) {
        throw "Built import probe missing: $probe"
    }

    $selfTestOutput = @(& $probe --self-test 2>&1)
    $selfTestExit = $LASTEXITCODE
    $selfTestOutput | ForEach-Object { Write-Host $_ }
    if ($selfTestExit -ne 0 -or
        @($selfTestOutput | Select-String -SimpleMatch 'RAVEN_IMPORT_PROBE_SELFTEST_PASSED').Count -eq 0) {
        throw 'Native import probe self-test failed; refusing live capture.'
    }

    Write-KnownDllEvidence

    $baselinePids = @(Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -in @('GoW','GodOfWar') } |
        Select-Object -ExpandProperty Id)

    Write-Host 'Launching GoW. Leave it at the main menu; the capture is automatic.'
    $bootstrap = Start-Process -FilePath $exe -WorkingDirectory $game -PassThru
    $bootstrapExitCode = $null
    $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)

    while ([DateTime]::UtcNow -lt $deadline -and $null -eq $target) {
        Start-Sleep -Milliseconds 500

        if ($null -eq $bootstrapExitCode) {
            try {
                $bootstrap.Refresh()
                if ($bootstrap.HasExited) { $bootstrapExitCode = $bootstrap.ExitCode }
            } catch {}
        }

        $candidates = @(Get-Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ProcessName -in @('GoW','GodOfWar') -and
                $baselinePids -notcontains $_.Id
            } |
            Sort-Object StartTime -Descending)

        foreach ($candidate in $candidates) {
            try {
                $candidate.Refresh()
                if (-not $candidate.HasExited) {
                    $target = $candidate
                    break
                }
            } catch {}
        }
    }

    if ($null -eq $target) {
        $bootstrapText = if ($null -eq $bootstrapExitCode) { 'unknown_or_running' } else { [string]$bootstrapExitCode }
        throw "No long-lived GoW process appeared within $StartupTimeoutSeconds seconds. bootstrap_exit_code=$bootstrapText"
    }

    Write-Host "Live GoW PID=$($target.Id). Waiting $SettleSeconds seconds (main-menu settle window)..."
    Start-Sleep -Seconds $SettleSeconds
    try {
        $target.Refresh()
        if ($target.HasExited) { throw 'Target GoW process exited during settle window.' }
    } catch {
        throw "GoW did not remain alive through settle window: $($_.Exception.Message)"
    }

    try {
        @(& "$env:SystemRoot\System32\tasklist.exe" /M XINPUT1_4.dll /FI "PID eq $($target.Id)" 2>&1) |
            Set-Content -LiteralPath $tasklistLog -Encoding UTF8
    } catch {
        "TASKLIST_QUERY_FAILED $($_.Exception.Message)" |
            Set-Content -LiteralPath $tasklistLog -Encoding UTF8
    }

    Write-Host 'Reading only GoW XINPUT1_4 import slots and their owning mapped image...'
    $probeOutput = @(& $probe --pid "$($target.Id)" --exe "$exe" --dll XINPUT1_4.dll 2>&1)
    $probeExit = $LASTEXITCODE
    $probeOutput | Set-Content -LiteralPath $probeLog -Encoding UTF8
    $probeOutput | ForEach-Object { Write-Host $_ }

    $probeComplete =
        $probeExit -eq 0 -and
        @($probeOutput | Select-String -SimpleMatch 'RAVEN_IMPORT_PROBE_COMPLETE').Count -gt 0

    @(
        "result=$(if ($probeComplete) { 'GOW_XINPUT_IAT_OWNER_CAPTURE_COMPLETE' } else { 'GOW_XINPUT_IAT_OWNER_CAPTURE_INCOMPLETE' })"
        "timestamp=$(Get-Date -Format o)"
        "branch=$ExpectedBranch"
        "bootstrap_pid=$($bootstrap.Id)"
        "bootstrap_exit_code=$(if ($null -eq $bootstrapExitCode) { 'n/a' } else { $bootstrapExitCode })"
        "game_pid=$($target.Id)"
        "settle_seconds=$SettleSeconds"
        "probe_exit_code=$probeExit"
        "probe_complete=$($probeComplete.ToString().ToLowerInvariant())"
        'proxy_installed=false'
        'process_writes=false'
        'save_writes=false'
        'progression_writes=false'
        'game_file_writes=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8

    Publish-Capture

    Write-Host "GOW_XINPUT_IAT_CAPTURE_PUSHED $((& git rev-parse HEAD).Trim())"
    Write-Host "Evidence: $relativeDir"
    Write-Host "probe_complete=$($probeComplete.ToString().ToLowerInvariant())"
    Write-Host 'GoW was left running intentionally; you can close it whenever you want.'
}
catch {
    $outer = $_
    try { $outer.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    try {
        @(
            'result=GOW_XINPUT_IAT_OWNER_CAPTURE_RUNNER_FAILED'
            "timestamp=$(Get-Date -Format o)"
            "reason=$($outer.Exception.Message)"
            'proxy_installed=false'
            'process_writes=false'
            'save_writes=false'
            'progression_writes=false'
            'game_file_writes=false'
        ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
    } catch {}
    try { Publish-Capture } catch {}
    throw
}
finally {
    Stop-LocalTranscript
}
