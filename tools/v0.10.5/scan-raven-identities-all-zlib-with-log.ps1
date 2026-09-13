param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-ravens-release-candidate'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/save-forensics/raven-identity-all-zlib-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$jsonPath = Join-Path $logDir 'identity-all-zlib.json'
$textPath = Join-Path $logDir 'identity-all-zlib.txt'
$pythonOutput = Join-Path $logDir 'python-output.txt'
$published = $false
$transcriptStarted = $false

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
            "active_save_opened=false"
            "game_written=false"
            "save_or_progression_written=false"
            "game_launched=false"
            "scan_only=true"
        ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8

        & git add -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git add of scan directory failed.' }
        & git diff --cached --quiet -- $relativeLogDir
        if ($LASTEXITCODE -eq 0) { return }
        & git commit -m "Archive exhaustive Raven identity scan $stamp" -- $relativeLogDir
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

    Write-Host '=== Completionist Map exhaustive Raven identity scan ==='
    Write-Host "Repository: $repo"

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) {
        throw "Wrong branch. Expected '$expectedBranch', found '$branch'."
    }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) {
        throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')"
    }

    $desktop = [Environment]::GetFolderPath('Desktop')
    if ([string]::IsNullOrWhiteSpace($desktop) -or -not (Test-Path -LiteralPath $desktop -PathType Container)) {
        throw "Desktop folder not found: $desktop"
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $python) { throw 'Python executable not found on PATH.' }

    $scanner = Join-Path $repo 'tools\v0.10.5\scan-raven-identities-all-zlib.py'
    if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) { throw "Scanner missing: $scanner" }

    Write-Host "Desktop frozen backups only: $desktop"
    Write-Host 'Active %USERPROFILE%\Saved Games\God of War is explicitly excluded.'

    & $python.Source $scanner --desktop $desktop --repo $repo --output-json $jsonPath --output-text $textPath 2>&1 |
        Tee-Object -FilePath $pythonOutput
    $scanExit = $LASTEXITCODE

    if ($scanExit -eq 0) {
        Write-Host 'RAVEN_IDENTITY_ALL_ZLIB_PASSED'
        Publish-Scan 'SCAN_PASSED'
    }
    else {
        throw "Python exhaustive Raven identity scanner exited with code $scanExit"
    }
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
