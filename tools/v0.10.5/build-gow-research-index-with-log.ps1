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
$bootstrapOutput = Join-Path $outDir 'bootstrap-output.txt'
$pythonOutput = Join-Path $outDir 'python-output.txt'
$published = $false
$transcript = $false

$indexRoot = Join-Path $repo '.research-index'
$packages = Join-Path $indexRoot 'python-packages'
$db = Join-Path $indexRoot 'gow-caebcb027980.sqlite'

function Invoke-PythonLogged {
    param(
        [Parameter(Mandatory=$true)][string[]]$Arguments,
        [Parameter(Mandatory=$true)][string]$LogPath,
        [switch]$Append
    )
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($Append) {
            & python @Arguments 2>&1 | Tee-Object -FilePath $LogPath -Append | Out-Host
        } else {
            & python @Arguments 2>&1 | Tee-Object -FilePath $LogPath | Out-Host
        }
        return $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldEap
    }
}

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
        "isolated_python_packages=$packages"
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
    New-Item -ItemType Directory -Force -Path $packages | Out-Null

    # Keep third-party research dependencies isolated under .research-index without
    # relying on Python's venv/ensurepip machinery. PYTHONPATH affects only this process tree.
    $oldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($oldPythonPath)) { $packages } else { "$packages;$oldPythonPath" }

    try {
        Write-Host 'Checking isolated Capstone dependency...'
        $capstoneExit = Invoke-PythonLogged -Arguments @('-c', 'import capstone; print(capstone.__version__)') -LogPath $bootstrapOutput
        if ($capstoneExit -ne 0) {
            Write-Host 'Installing Capstone into .research-index\python-packages...'
            $pipExit = Invoke-PythonLogged -Arguments @('-m','pip','install','--disable-pip-version-check','--target',$packages,'--upgrade','capstone>=5,<6') -LogPath $bootstrapOutput -Append
            if ($pipExit -ne 0) {
                throw "Capstone bootstrap failed with exit code $pipExit. Full output archived in $bootstrapOutput"
            }
            $verifyExit = Invoke-PythonLogged -Arguments @('-c', 'import capstone; print(capstone.__version__)') -LogPath $bootstrapOutput -Append
            if ($verifyExit -ne 0) {
                throw "Capstone import still fails after installation (exit $verifyExit). Full output archived in $bootstrapOutput"
            }
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

        $pythonExit = Invoke-PythonLogged -Arguments $argsList -LogPath $pythonOutput
        if ($pythonExit -ne 0) {
            throw "Indexer exited $pythonExit. Full Python output archived in $pythonOutput"
        }
    }
    finally {
        $env:PYTHONPATH = $oldPythonPath
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
