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
$relativeLogDir = "archive/field-logs/source-scans/gameobject-lua-api-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$scanner = Join-Path $repo 'tools\v0.10.5\scan-gameobject-lua-api.py'
$outputJson = Join-Path $logDir 'gameobject-lua-api.json'
$outputText = Join-Path $logDir 'gameobject-lua-api.txt'
$resultPath = Join-Path $logDir 'result.txt'
$transcriptStarted = $false

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Completionist Map GameObject Lua API scan ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"
    Write-Host 'Read-only, version-locked GoW.exe scan. God of War is not launched.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch. Expected '$expectedBranch', found '$branch'." }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing to run with staged changes: $($staged -join ', ')" }
    foreach ($path in @($scanner, (Join-Path $GameRoot 'GoW.exe'))) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
    }

    & python $scanner --game-root $GameRoot --output-json $outputJson --output-text $outputText
    if ($LASTEXITCODE -ne 0) { throw "GameObject API scanner failed with exit $LASTEXITCODE." }

    @(
        'result=GAMEOBJECT_LUA_API_SCAN_PASSED'
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        'game_launched=false'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'scan_only=true'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8

    Stop-LocalTranscript
    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git commit -m "Archive GameObject Lua API scan $stamp" -- $relativeLogDir | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    & git push origin "HEAD:$expectedBranch" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    Write-Host 'GAMEOBJECT_LUA_API_SCAN_PASSED_AND_PUSHED' -ForegroundColor Green
}
catch {
    try {
        @(
            'result=GAMEOBJECT_LUA_API_SCAN_FAILED'
            "timestamp=$(Get-Date -Format o)"
            "branch=$expectedBranch"
            "error=$($_.Exception.Message)"
            'game_launched=false'
            'active_save_opened=false'
            'game_written=false'
            'save_or_progression_written=false'
            'scan_only=true'
        ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
    } catch {}
    Write-Host "GAMEOBJECT_LUA_API_SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Stop-LocalTranscript
    try {
        & git add -- $relativeLogDir
        if ($LASTEXITCODE -eq 0) {
            & git commit -m "Archive GameObject Lua API scan failure $stamp" -- $relativeLogDir | Out-Host
            if ($LASTEXITCODE -eq 0) { & git push origin "HEAD:$expectedBranch" | Out-Host }
        }
    } catch {}
    exit 1
}
finally {
    Stop-LocalTranscript
}
