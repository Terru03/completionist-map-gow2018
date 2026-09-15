param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$exe = 'G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relative = "archive/field-logs/source-scans/gow-codec-inverse-dataflow-$stamp"
$outDir = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$json = Join-Path $outDir 'gow-codec-inverse-dataflow.json'
$text = Join-Path $outDir 'gow-codec-inverse-dataflow.txt'
$pythonOutput = Join-Path $outDir 'python-output.txt'
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
        'analysis=gow_codec_inverse_dataflow'
        'exe_rescanned=targeted-codec-band-only'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

    & git add -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relative
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Archive GoW codec inverse dataflow $stamp" -- $relative | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin "HEAD:$expectedBranch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff failed.'
    }
    $script:published = $true
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true

    Write-Host '=== Completionist Map broad codec inverse dataflow ==='
    Write-Host 'Targeted read-only Capstone pass over 0x7E7000-0x7EA600; no game launch/save I/O.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing staged changes: $($staged -join ', ')" }

    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "GoW.exe missing: $exe" }
    $scriptPath = Join-Path $repo 'tools\v0.10.5\trace-gow-codec-inverse-dataflow.py'
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw 'Codec inverse tracer missing.' }

    $pythonCmd = Get-Command python.exe -ErrorAction Stop
    $pythonExe = $pythonCmd.Source
    Write-Host "PYTHON_EXE=$pythonExe"
    Write-Host "PYTHON_SCRIPT=$scriptPath"

    & $pythonExe -m py_compile $scriptPath 2>&1 | Tee-Object -FilePath $pythonOutput
    if ($LASTEXITCODE -ne 0) { throw 'Python syntax preflight failed.' }

    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $pythonExe -I $scriptPath --exe $exe --output-json $json --output-text $text 2>&1 | Tee-Object -FilePath $pythonOutput -Append
        $pythonExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldEap
    }
    if ($pythonExit -ne 0) { throw "Codec inverse tracer exited $pythonExit. Full output: $pythonOutput" }

    Publish 'ANALYSIS_PASSED'
    Write-Host 'GOW_CODEC_INVERSE_DATAFLOW_PASSED_AND_PUSHED' -ForegroundColor Green
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
