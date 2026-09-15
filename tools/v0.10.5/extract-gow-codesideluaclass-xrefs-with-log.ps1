param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relative = "archive/field-logs/source-scans/gow-codesideluaclass-xrefs-$stamp"
$outDir = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$json = Join-Path $outDir 'gow-codesideluaclass-xrefs.json'
$text = Join-Path $outDir 'gow-codesideluaclass-xrefs.txt'
$pythonOutput = Join-Path $outDir 'python-output.txt'
$resultPath = Join-Path $outDir 'result.txt'
$published = $false
$transcript = $false

function Publish([string]$Result) {
    if ($script:published) { return }
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        'analysis=gow_codesideluaclass_xrefs'
        'analysis_mode=read-only-postprocess'
        'game_exe_opened=false'
        'active_save_opened=false'
        'frozen_save_opened=false'
        'game_launched=false'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8

    & git add -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'git add archive failed.' }
    & git diff --cached --quiet -- $relative
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Archive GoW CodeSideLuaClass xrefs $stamp" -- $relative | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit archive failed.' }
        & git push origin "HEAD:$expectedBranch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff archive check failed.'
    }
    $script:published = $true
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true
    Write-Host '=== Completionist Map GoW CodeSideLuaClass xrefs ==='
    Write-Host 'Read-only post-process of the already archived userdata trace. No GoW.exe/save access.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing staged changes: $($staged -join ', ')" }

    $scriptPath = Join-Path $repo 'tools\v0.10.5\extract-gow-codesideluaclass-xrefs.py'
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw "Extractor missing: $scriptPath" }
    $pythonExe = (Get-Command python.exe -ErrorAction Stop).Source

    & $pythonExe -I -m py_compile $scriptPath 2>&1 | Tee-Object -FilePath $pythonOutput
    if ($LASTEXITCODE -ne 0) { throw 'Python syntax preflight failed.' }
    & $pythonExe -I $scriptPath --self-test 2>&1 | Tee-Object -FilePath $pythonOutput -Append
    if ($LASTEXITCODE -ne 0) { throw 'Extractor self-test failed.' }
    & $pythonExe -I $scriptPath --output-json $json --output-text $text 2>&1 | Tee-Object -FilePath $pythonOutput -Append
    if ($LASTEXITCODE -ne 0) { throw "Extractor exited $LASTEXITCODE." }

    $report = Get-Content -Raw -LiteralPath $json | ConvertFrom-Json
    if ($report.exact_lookup_corrected_status -ne 'PASS_EXACT_USERDATA_CLASS_LOOKUP') {
        throw "Unexpected lookup status: $($report.exact_lookup_corrected_status)"
    }
    if ($report.xref_count -ne 8) { throw "Unexpected xref count: $($report.xref_count)" }
    Publish 'ANALYSIS_PASSED'
    Write-Host 'GOW_CODESIDELUACLASS_XREFS_ARCHIVED_AND_PUSHED' -ForegroundColor Green
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "ANALYSIS_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish 'ANALYSIS_FAILED' } catch { Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    if ($transcript) { try { Stop-Transcript | Out-Null } catch {} }
}
