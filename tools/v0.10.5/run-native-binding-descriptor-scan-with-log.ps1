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
$relativeLogDir = "archive/field-logs/source-scans/native-binding-descriptors-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$jsonOut = Join-Path $logDir 'descriptors.json'
$textOut = Join-Path $logDir 'descriptors.txt'
$published = $false
$transcriptStarted = $false

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
        'scan_only=true'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8
}

function Publish-Scan([string]$Result) {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    Write-Result $Result

    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add of descriptor scan directory failed.' }
    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 0) { return }
    if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged descriptor scan changes.' }

    & git commit -m "Archive native binding descriptor scan $stamp" -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git commit of descriptor scan failed.' }
    & git push origin "HEAD:$expectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'git push of descriptor scan failed.' }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map native binding descriptor layout scan ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"
    Write-Host 'Read-only GoW.exe descriptor scan. Game/save/progression are not written and the game is not launched.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) {
        throw "Wrong branch. Expected '$expectedBranch', found '$branch'."
    }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect pre-existing staged changes.' }
    if ($staged.Count -gt 0) {
        throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')"
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $python) { throw 'Python executable not found on PATH.' }

    $scriptPath = Join-Path $repo 'tools/v0.10.5/analyze-native-binding-descriptors.py'
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        throw "Descriptor analyzer missing: $scriptPath"
    }

    & $python.Source $scriptPath --game-root $GameRoot --output-json $jsonOut --output-text $textOut 2>&1 |
        Tee-Object -FilePath (Join-Path $logDir 'python-output.txt')
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Descriptor analyzer failed with exit code $code" }

    if (-not (Test-Path -LiteralPath $textOut -PathType Leaf)) { throw 'Descriptor text report missing.' }
    $head = @(Get-Content -LiteralPath $textOut -TotalCount 120)
    foreach ($line in $head) { Write-Host $line }

    Write-Host "Output: $relativeLogDir"
    Write-Host 'NATIVE_BINDING_DESCRIPTOR_SCAN_PASSED'
    Publish-Scan 'SCAN_PASSED'
    Write-Host 'SCAN_PASSED_AND_PUSHED'
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Scan 'SCAN_FAILED' } catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 1
}
finally {
    Stop-LocalTranscript
}
