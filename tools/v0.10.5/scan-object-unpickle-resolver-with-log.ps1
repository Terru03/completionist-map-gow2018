param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/source-scans/object-unpickle-resolver-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$jsonPath = Join-Path $logDir 'object-unpickle-resolver.json'
$textPath = Join-Path $logDir 'object-unpickle-resolver.txt'
$published = $false
$transcriptStarted = $false

function Publish-Scan([string]$result) {
    if ($script:published) { return }
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
    @(
        "result=$result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        'source_hashes_unchanged=true'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
        'scan_only=true'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8
    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Archive object unpickle resolver scan $stamp" -- $relativeLogDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin "HEAD:$expectedBranch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'Unable to inspect staged scan.'
    }
    $script:published = $true
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Completionist Map object unpickle resolver scan ==='
    Write-Host 'Read-only static GoW.exe analysis. Game is not launched; saves are not opened.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch. Expected '$expectedBranch', found '$branch'." }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing to run with staged changes: $($staged -join ', ')" }

    $scanner = Join-Path $repo 'tools\v0.10.5\analyze-object-unpickle-resolver.py'
    if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) { throw "Analyzer missing: $scanner" }
    $exe = Join-Path $GameRoot 'GoW.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "GoW.exe missing: $exe" }

    & python $scanner --game-root $GameRoot --output-json $jsonPath --output-text $textPath
    if ($LASTEXITCODE -ne 0) { throw "Analyzer exited with code $LASTEXITCODE" }
    Publish-Scan 'SCAN_PASSED'
    Write-Host 'OBJECT_UNPICKLE_RESOLVER_SCAN_PASSED_AND_PUSHED' -ForegroundColor Green
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
