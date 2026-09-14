param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-ravens-release-candidate'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$intended = @(
    'tools/v0.10.5/all-ravens-map-runtime.lua',
    'tools/v0.10.5/test_all_ravens_lua.py',
    'tools/v0.10.5/raven_runtime_model.py',
    'tools/v0.10.5/test_raven_runtime_model.py',
    'catalogue/odins-ravens.json',
    'tools/v0.10.5/raven_catalogue.py',
    'tools/v0.10.5/test_raven_catalogue.py',
    'docs/research/all-ravens-release-gate.md'
)

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/all-ravens-hardening-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$transcriptStarted = $false
$published = $false
$patchStarted = $false

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
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
        'offline_only=true'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8
}

function Publish-Hardening([string]$Result, [bool]$IncludePatchedFiles) {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    Write-Result $Result

    $paths = @($relativeLogDir)
    if ($IncludePatchedFiles) { $paths = @($intended) + $paths }

    & git add -- @paths
    if ($LASTEXITCODE -ne 0) { throw 'git add of explicit hardening paths failed.' }

    & git diff --cached --quiet -- @paths
    if ($LASTEXITCODE -eq 0) { throw 'Nothing was staged for hardening publication.' }
    if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged hardening changes.' }

    $message = if ($Result -eq 'HARDENING_PASSED') {
        "Harden all-Ravens runtime and archive offline proof $stamp"
    } else {
        "Archive failed all-Ravens hardening $stamp"
    }
    & git commit -m $message -- @paths
    if ($LASTEXITCODE -ne 0) { throw 'git commit of hardening result failed.' }
    & git push origin "HEAD:$expectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'git push of hardening result failed.' }
}

function Invoke-PythonTest([string]$Name, [string]$RelativePath, $PythonCommand) {
    $path = Join-Path $repo $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing test: $RelativePath" }
    $out = Join-Path $logDir ("test-$Name.txt")
    Write-Host "=== TEST $Name ==="
    & $PythonCommand.Source $path 2>&1 | Tee-Object -FilePath $out
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Test '$Name' failed with exit code $code" }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map v0.10.5 all-Ravens hardening ==='
    Write-Host "Repository: $repo"
    Write-Host 'Offline/source-only run. God of War is not launched and active saves are not opened.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) {
        throw "Wrong branch. Expected '$expectedBranch', found '$branch'."
    }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect pre-existing staged changes.' }
    if ($staged.Count -gt 0) {
        throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')"
    }

    $dirtyIntended = @(& git status --porcelain -- @intended)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect intended hardening paths.' }
    if ($dirtyIntended.Count -gt 0) {
        throw "Refusing to overwrite pre-existing local edits in hardening paths: $($dirtyIntended -join '; ')"
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $python) { throw 'Python executable not found on PATH.' }

    $patcher = Join-Path $repo 'tools/v0.10.5/apply-all-ravens-hardening.py'
    if (-not (Test-Path -LiteralPath $patcher -PathType Leaf)) { throw "Patcher missing: $patcher" }

    Write-Host '=== APPLY GUARDED PATCH ==='
    $patchStarted = $true
    & $python.Source $patcher 2>&1 | Tee-Object -FilePath (Join-Path $logDir 'patcher-output.txt')
    $patchCode = $LASTEXITCODE
    if ($patchCode -ne 0) { throw "Hardening patcher failed with exit code $patchCode" }

    & git diff --check -- @intended 2>&1 | Tee-Object -FilePath (Join-Path $logDir 'git-diff-check.txt')
    if ($LASTEXITCODE -ne 0) { throw 'git diff --check failed for hardened files.' }

    Invoke-PythonTest 'raven-catalogue' 'tools/v0.10.5/test_raven_catalogue.py' $python
    Invoke-PythonTest 'raven-runtime-model' 'tools/v0.10.5/test_raven_runtime_model.py' $python
    Invoke-PythonTest 'all-ravens-build' 'tools/v0.10.5/test_all_ravens_build.py' $python
    Invoke-PythonTest 'all-ravens-lua' 'tools/v0.10.5/test_all_ravens_lua.py' $python

    $transaction = Join-Path $repo 'tools/v0.10.5/test-all-ravens-transaction.ps1'
    if (-not (Test-Path -LiteralPath $transaction -PathType Leaf)) { throw "Missing transaction test: $transaction" }
    Write-Host '=== TEST all-ravens-transaction ==='
    & pwsh.exe -NoProfile -ExecutionPolicy Bypass -File $transaction 2>&1 |
        Tee-Object -FilePath (Join-Path $logDir 'test-all-ravens-transaction.txt')
    $transactionCode = $LASTEXITCODE
    if ($transactionCode -ne 0) { throw "Transaction test failed with exit code $transactionCode" }

    # Freeze a compact proof of exactly what is about to be committed.
    & git diff -- @intended | Set-Content -LiteralPath (Join-Path $logDir 'hardening.patch') -Encoding UTF8
    @(& git diff --name-only -- @intended) |
        Set-Content -LiteralPath (Join-Path $logDir 'changed-files.txt') -Encoding UTF8

    Write-Host 'ALL_RAVENS_HARDENING_PASSED'
    Publish-Hardening 'HARDENING_PASSED' $true
    Write-Host 'ALL_RAVENS_HARDENING_PASSED_AND_PUSHED'
}
catch {
    $failure = $_.Exception.ToString()
    try { $failure | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "ALL_RAVENS_HARDENING_FAILED: $($_.Exception.Message)" -ForegroundColor Red

    # The intended paths were verified clean before patching, so restoring only these
    # explicit paths cannot destroy unrelated local work. Preserve the failed diff first.
    if ($patchStarted) {
        try {
            & git diff -- @intended | Set-Content -LiteralPath (Join-Path $logDir 'failed-hardening.patch') -Encoding UTF8
            & git restore -- @intended
            if ($LASTEXITCODE -ne 0) { throw 'git restore of failed hardening paths failed.' }
        }
        catch {
            try { $_.Exception.ToString() | Add-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
            Write-Host "FAILED_PATCH_RESTORE_ERROR: $($_.Exception.Message)" -ForegroundColor Red
        }
    }

    try {
        Publish-Hardening 'HARDENING_FAILED' $false
        Write-Host 'FAILED_HARDENING_LOG_PUSHED'
    }
    catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host 'Only because publication failed, copy the console output manually.' -ForegroundColor Yellow
    }
    exit 1
}
finally {
    Stop-LocalTranscript
}
