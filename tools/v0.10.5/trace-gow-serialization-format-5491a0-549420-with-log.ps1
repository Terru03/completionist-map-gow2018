param(
    [string]$BootstrapLog = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$branch = 'codex/all-collectibles-production-research'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script = Join-Path $PSScriptRoot 'trace-gow-serialization-format-5491a0-549420.py'
$exe = 'G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe'
$db = Join-Path $repo '.research-index\gow-caebcb027980.sqlite'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$archive = Join-Path $repo "archive\field-logs\source-scans\gow-serialization-format-5491a0-549420-$timestamp"
New-Item -ItemType Directory -Force -Path $archive | Out-Null

$consoleLog = Join-Path $archive 'console-log.txt'
$pythonOut = Join-Path $archive 'python-output.txt'
$jsonOut = Join-Path $archive 'gow-serialization-format-5491a0-549420.json'
$textOut = Join-Path $archive 'gow-serialization-format-5491a0-549420.txt'
$resultOut = Join-Path $archive 'result.txt'
$errorOut = Join-Path $archive 'error.txt'
$gitStateOut = Join-Path $archive 'git-state.txt'

if ($BootstrapLog -and (Test-Path -LiteralPath $BootstrapLog -PathType Leaf)) {
    Copy-Item -LiteralPath $BootstrapLog -Destination (Join-Path $archive 'bootstrap-sync.txt') -Force
}

function Write-GitState {
    Push-Location $repo
    try {
        @(
            "captured_at=$((Get-Date).ToString('o'))"
            "branch=$(git branch --show-current)"
            "head=$(git rev-parse HEAD)"
            "remote_head=$(git rev-parse origin/$branch)"
            'status_begin'
            (git status --short)
            'status_end'
        ) | Set-Content -LiteralPath $gitStateOut -Encoding UTF8
    }
    finally {
        Pop-Location
    }
}

function Push-ArchiveCommit {
    param([Parameter(Mandatory=$true)][string]$Message)

    Push-Location $repo
    try {
        git add -- $archive
        if ($LASTEXITCODE -ne 0) { throw "git add failed with exit code $LASTEXITCODE" }

        $staged = git diff --cached --name-only
        if (-not $staged) { throw 'No archive files were staged for the GitHub report.' }

        git commit -m $Message
        if ($LASTEXITCODE -ne 0) { throw "git commit failed with exit code $LASTEXITCODE" }

        git push origin $branch
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Initial push rejected/failed; rebasing once against remote and retrying.'
            git pull --rebase origin $branch
            if ($LASTEXITCODE -ne 0) { throw "git pull --rebase failed with exit code $LASTEXITCODE" }
            git push origin $branch
            if ($LASTEXITCODE -ne 0) { throw "git push retry failed with exit code $LASTEXITCODE" }
        }
    }
    finally {
        Pop-Location
    }
}

Start-Transcript -Path $consoleLog -Force | Out-Null
try {
    Write-Host '=== Completionist Map 0x5491A0 / 0x549420 serialization-format trace ==='
    Write-Host 'Static analysis only. No game launch and no save I/O.'

    Push-Location $repo
    try {
        $currentBranch = (git branch --show-current).Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Unable to determine current Git branch.' }
        if ($currentBranch -ne $branch) {
            throw "Wrong branch: '$currentBranch'. Expected '$branch'."
        }
        git fetch origin $branch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "git fetch failed with exit code $LASTEXITCODE" }
    }
    finally {
        Pop-Location
    }

    Write-GitState

    if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Missing Python script: $script" }
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Missing GoW.exe: $exe" }
    if (-not (Test-Path -LiteralPath $db -PathType Leaf)) { throw "Missing reusable research index: $db" }

    $python = (Get-Command python.exe -ErrorAction Stop).Source
    Write-Host "PYTHON_EXE=$python"
    Write-Host "PYTHON_SCRIPT=$script"
    Write-Host "INDEX=$db"

    & $python -I -m py_compile $script
    if ($LASTEXITCODE -ne 0) { throw "py_compile failed with exit code $LASTEXITCODE" }

    & $python -I $script --exe $exe --db $db --output-json $jsonOut --output-text $textOut 2>&1 |
        Tee-Object -FilePath $pythonOut
    if ($LASTEXITCODE -ne 0) {
        throw "Serialization-format tracer exited $LASTEXITCODE. Full output: $pythonOut"
    }

    @(
        'result=ANALYSIS_PASSED'
        "timestamp=$((Get-Date).ToString('o'))"
        "branch=$branch"
        'analysis=gow_serialization_format_5491a0_549420'
        'targets=0x5491A0,0x549420'
        'save_anchor=0x7E9190'
        'restore_anchor=0x7E9550'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
    ) | Set-Content -LiteralPath $resultOut -Encoding UTF8

    Write-GitState
    Stop-Transcript | Out-Null
    Push-ArchiveCommit -Message "Archive GoW 5491A0/549420 serialization trace $timestamp"
    Write-Host 'GOW_SERIALIZATION_FORMAT_5491A0_549420_PASSED_AND_PUSHED'
}
catch {
    $_ | Out-String | Set-Content -LiteralPath $errorOut -Encoding UTF8
    @(
        'result=ANALYSIS_FAILED'
        "timestamp=$((Get-Date).ToString('o'))"
        "branch=$branch"
        'analysis=gow_serialization_format_5491a0_549420'
        'targets=0x5491A0,0x549420'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
    ) | Set-Content -LiteralPath $resultOut -Encoding UTF8

    try { Write-GitState } catch {}
    try { Stop-Transcript | Out-Null } catch {}

    try {
        Push-ArchiveCommit -Message "Archive failed GoW 5491A0/549420 serialization trace $timestamp"
    }
    catch {
        Write-Warning "Could not push failure archive automatically: $($_.Exception.Message)"
    }
    throw
}
