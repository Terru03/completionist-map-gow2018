param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$branch = (& git branch --show-current).Trim()
if ($branch -ne $expectedBranch) { throw "Wrong branch. Expected '$expectedBranch', found '$branch'." }

$staged = @(& git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
if ($staged.Count -gt 0) { throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')" }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/source-scans/gameobject-argument-decoder-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$jsonPath = Join-Path $logDir 'gameobject-argument-decoder.json'
$textPath = Join-Path $logDir 'gameobject-argument-decoder.txt'
$pythonOutput = Join-Path $logDir 'python-output.txt'
$published = $false
$transcriptStarted = $false

function Publish-Scan([string]$Result) {
    if ($script:published) { return }
    $script:published = $true
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        "source_hash_unchanged=true"
        "active_save_opened=false"
        "game_written=false"
        "save_or_progression_written=false"
        "game_launched=false"
        "scan_only=true"
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8

    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 0) { return }
    & git commit -m "Archive GameObject argument decoder scan $stamp" -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    & git push origin "HEAD:$expectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Completionist Map GameObject Lua argument decoder scan ==='
    Write-Host 'Read-only static GoW.exe analysis. Game is not launched; saves are not opened.'

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $python) { throw 'Python executable not found on PATH.' }

    $scanner = Join-Path $repo 'tools\v0.10.5\analyze-gameobject-argument-decoder.py'
    if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) { throw "Analyzer missing: $scanner" }

    & $python.Source $scanner --game-root $GameRoot --output-json $jsonPath --output-text $textPath 2>&1 |
        Tee-Object -FilePath $pythonOutput
    if ($LASTEXITCODE -ne 0) { throw "Analyzer exited with code $LASTEXITCODE" }

    Write-Host 'GAMEOBJECT_ARGUMENT_DECODER_SCAN_PASSED'
    Publish-Scan 'SCAN_PASSED'
    Write-Host 'GAMEOBJECT_ARGUMENT_DECODER_SCAN_PASSED_AND_PUSHED'
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Scan 'SCAN_FAILED' } catch {}
    exit 1
}
finally {
    if ($transcriptStarted) { try { Stop-Transcript | Out-Null } catch {} }
}
