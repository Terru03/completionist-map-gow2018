param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relative = "archive/field-logs/source-scans/gow-research-index-$stamp"
$outDir = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$manifest = Join-Path $outDir 'manifest.json'
$hotJson = Join-Path $outDir 'hot-report.json'
$hotText = Join-Path $outDir 'hot-report.txt'
$pythonOutput = Join-Path $outDir 'python-output.txt'
$published = $false
$transcript = $false

$indexRoot = Join-Path $repo '.research-index'
$venv = Join-Path $indexRoot 'venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
$db = Join-Path $indexRoot 'gow-caebcb027980.sqlite'

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
        "local_index=$db"
        'source_hashes_unchanged=true'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
        'scan_only=true'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

    & git add -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relative
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Archive reusable GoW research index $stamp" -- $relative | Out-Host
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

    Write-Host '=== Completionist Map reusable God of War research index ==='
    Write-Host 'One-time static index build. GoW.exe + extracted Lua + game file manifest.'
    Write-Host 'The local SQLite index is reused by later queries; it is not committed to Git.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing staged changes: $($staged -join ', ')" }

    $builder = Join-Path $repo 'tools\v0.10.5\build-gow-research-index.py'
    if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) { throw 'Index builder missing.' }
    if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "Game root missing: $GameRoot" }
    if (-not (Test-Path -LiteralPath (Join-Path $GameRoot 'GoW.exe') -PathType Leaf)) { throw 'GoW.exe missing.' }

    New-Item -ItemType Directory -Force -Path $indexRoot | Out-Null
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        Write-Host 'Creating isolated research-index Python environment...'
        & python -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'python -m venv failed.' }
    }

    $capstoneOk = $false
    & $venvPython -c 'import capstone; print(capstone.__version__)' 2>$null | Out-Host
    if ($LASTEXITCODE -eq 0) { $capstoneOk = $true }
    if (-not $capstoneOk) {
        Write-Host 'Installing Capstone into the isolated research-index environment...'
        & $venvPython -m pip install --disable-pip-version-check 'capstone>=5,<6' | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Capstone installation failed.' }
    }

    $argsList = @(
        $builder,
        '--game-root', $GameRoot,
        '--db', $db,
        '--manifest', $manifest,
        '--hot-json', $hotJson,
        '--hot-text', $hotText
    )
    if ($Rebuild) { $argsList += '--rebuild' }

    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $venvPython @argsList 2>&1 | Tee-Object -FilePath $pythonOutput
        $pythonExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldEap
    }

    if ($pythonExit -ne 0) {
        throw "Indexer exited $pythonExit. Full Python output archived in $pythonOutput"
    }

    Publish 'INDEX_PASSED'
    Write-Host 'GOW_RESEARCH_INDEX_BUILD_PASSED_AND_PUSHED' -ForegroundColor Green
    Write-Host "Local reusable index: $db" -ForegroundColor Cyan
}
catch {
    try {
        $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8
    } catch {}
    Write-Host "INDEX_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try {
        Publish 'INDEX_FAILED'
    } catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 1
}
finally {
    if ($transcript) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}
