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
$relativeLogDir = "archive/field-logs/source-scans/lua-registration-exhaustive-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$jsonPath = Join-Path $logDir 'registration-exhaustive.json'
$textPath = Join-Path $logDir 'registration-exhaustive.txt'
$pythonOutput = Join-Path $logDir 'python-output.txt'
$summaryPath = Join-Path $logDir 'summary.txt'
$published = $false
$transcriptStarted = $false
$hashesUnchanged = 'unknown'

function Publish-Scan([string]$Result) {
    if ($script:published) { return }
    $script:published = $true
    try {
        if ($script:transcriptStarted) {
            Stop-Transcript | Out-Null
            $script:transcriptStarted = $false
        }

        @(
            "result=$Result"
            "timestamp=$(Get-Date -Format o)"
            "branch=$expectedBranch"
            "source_hashes_unchanged=$script:hashesUnchanged"
            "active_save_opened=false"
            "game_written=false"
            "save_or_progression_written=false"
            "game_launched=false"
            "scan_only=true"
        ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8

        $allFiles = @(Get-ChildItem -LiteralPath $logDir -File -Recurse)
        foreach ($file in $allFiles) {
            if ($file.Length -gt 15MB) {
                throw "Refusing to publish oversized scan file: $($file.FullName) ($($file.Length) bytes)"
            }
        }

        & git add -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git add of scan directory failed.' }

        $staged = @(& git diff --cached --name-only)
        if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged paths before publication.' }
        $foreign = @($staged | Where-Object { -not $_.StartsWith("$relativeLogDir/") })
        if ($foreign.Count -gt 0) {
            throw "Refusing foreign staged paths: $($foreign -join ', ')"
        }

        & git diff --cached --quiet -- $relativeLogDir
        if ($LASTEXITCODE -eq 0) { return }
        & git commit -m "Archive exhaustive native Lua registrations $stamp" -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git commit of scan directory failed.' }
        & git push origin "HEAD:$expectedBranch"
        if ($LASTEXITCODE -ne 0) { throw 'git push of scan directory failed.' }
    }
    catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map exhaustive native Lua registration scan ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) {
        throw "Wrong branch. Expected '$expectedBranch', found '$branch'."
    }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) {
        throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')"
    }

    $gowProcess = Get-Process -Name 'GoW' -ErrorAction SilentlyContinue
    if ($null -ne $gowProcess) {
        throw 'GoW.exe is running. Close the game before this read-only executable scan.'
    }

    $game = [IO.Path]::GetFullPath($GameRoot)
    if (-not (Test-Path -LiteralPath $game -PathType Container)) {
        throw "Game root not found: $game"
    }
    $exe = Join-Path $game 'GoW.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "GoW.exe not found: $exe"
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $python) { throw 'Python executable not found on PATH.' }

    $scanner = Join-Path $repo 'tools\v0.10.5\enumerate-gow-lua-registration-tables-exhaustive.py'
    if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) {
        throw "Analyzer missing: $scanner"
    }

    Write-Host 'Read-only scan: GoW.exe direct registration metadata only.'
    Write-Host 'This scan does not open the active save directory and does not launch the game.'

    & $python.Source $scanner --game-root $game --output-json $jsonPath --output-text $textPath 2>&1 |
        Tee-Object -FilePath $pythonOutput
    $scanExit = $LASTEXITCODE
    if ($scanExit -ne 0) {
        throw "Python exhaustive registration analyzer exited with code $scanExit"
    }

    $report = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json -Depth 100
    if ($report.scan_kind -ne 'read_only_exhaustive_direct_lua_registration_enumeration') {
        throw "Unexpected scan kind: $($report.scan_kind)"
    }
    if (-not $report.safety.source_hashes_unchanged -or
        $report.safety.active_save_opened -or
        $report.safety.game_written -or
        $report.safety.save_or_progression_written -or
        $report.safety.game_launched) {
        throw 'Safety contract failed in generated report.'
    }
    if ($report.strides_scanned.Count -lt 7) {
        throw 'Stride coverage unexpectedly incomplete.'
    }

    $script:hashesUnchanged = 'true'
    @(
        'EXHAUSTIVE_LUA_REGISTRATION_SCAN_COMPLETED'
        "exe_sha256=$($report.exe_sha256)"
        "direct_name_function_pairs=$($report.direct_name_function_pairs)"
        "candidate_table_count=$($report.candidate_table_count)"
        "canonical_table_count=$($report.canonical_table_count)"
        "interesting_registration_count=$($report.interesting_registration_count)"
        'scope=direct absolute name-pointer + executable function-pointer records at 8-byte alignment; not all possible binding mechanisms'
        'runtime_generation_allowed=false'
        'source_hashes_unchanged=true'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
    ) | Set-Content -LiteralPath $summaryPath -Encoding UTF8

    Get-Content -LiteralPath $summaryPath | ForEach-Object { Write-Host $_ }
    Publish-Scan 'SCAN_PASSED'
}
catch {
    $message = $_.Exception.ToString()
    try { $message | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Scan 'SCAN_FAILED' } catch {
        Write-Host 'The scan failed and its log could not be published. Only then copy console output manually.' -ForegroundColor Red
    }
    exit 1
}
finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}
