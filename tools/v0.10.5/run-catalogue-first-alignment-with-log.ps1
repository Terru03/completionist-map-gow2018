$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = 'codex/all-collectibles-production-research'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDir = Join-Path $repo 'archive\field-logs\local-handoffs'
$log = Join-Path $logDir "all-ravens-catalogue-first-$stamp.txt"
$logRel = "archive/field-logs/local-handoffs/all-ravens-catalogue-first-$stamp.txt"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $repo

function Invoke-Logged {
    param(
        [Parameter(Mandatory=$true)][string]$Label,
        [Parameter(Mandatory=$true)][string]$Command
    )
    "`n=== $Label ===" | Add-Content -LiteralPath $log -Encoding utf8
    $output = & $env:ComSpec /d /s /c "$Command 2>&1"
    $code = $LASTEXITCODE
    if ($null -ne $output) { $output | Add-Content -LiteralPath $log -Encoding utf8 }
    "exit_code=$code" | Add-Content -LiteralPath $log -Encoding utf8
    return $code
}

function Push-LogOnly {
    param([string]$Failure)
    "`n=== RESULT ===" | Add-Content -LiteralPath $log -Encoding utf8
    "RESULT=FAILED" | Add-Content -LiteralPath $log -Encoding utf8
    "FAILED_STEP=$Failure" | Add-Content -LiteralPath $log -Encoding utf8

    # This checkout is the isolated research clone. Revert only work produced by
    # this run, while keeping the untracked handoff log itself.
    & $env:ComSpec /d /s /c "git reset --hard HEAD >nul 2>&1"
    & $env:ComSpec /d /s /c "git add -- $logRel >nul 2>&1"
    & $env:ComSpec /d /s /c "git commit -m ""logs: capture failed all-Ravens catalogue-first validation $stamp"" >nul 2>&1"
    if ($LASTEXITCODE -eq 0) {
        & $env:ComSpec /d /s /c "git push origin $branch >nul 2>&1"
    }
}

"=== ALL-RAVENS CATALOGUE-FIRST VALIDATION ===" | Set-Content -LiteralPath $log -Encoding utf8
"timestamp=$stamp" | Add-Content -LiteralPath $log -Encoding utf8
"branch=$branch" | Add-Content -LiteralPath $log -Encoding utf8

$trackedDirty = & $env:ComSpec /d /s /c "git status --porcelain --untracked-files=no"
if ($LASTEXITCODE -ne 0) {
    Push-LogOnly 'git-status'
    Write-Host 'DONE'
    exit 0
}
if ($trackedDirty) {
    "Tracked checkout was dirty before validation; refusing to modify it." | Add-Content -LiteralPath $log -Encoding utf8
    $trackedDirty | Add-Content -LiteralPath $log -Encoding utf8
    & $env:ComSpec /d /s /c "git add -- $logRel >nul 2>&1"
    & $env:ComSpec /d /s /c "git commit -m ""logs: refuse catalogue-first validation on dirty checkout $stamp"" >nul 2>&1"
    if ($LASTEXITCODE -eq 0) { & $env:ComSpec /d /s /c "git push origin $branch >nul 2>&1" }
    Write-Host 'DONE'
    exit 0
}

$gameCandidates = @(
    'G:\SteamLibrary\steamapps\common\GodOfWar',
    'D:\SteamLibrary\steamapps\common\GodOfWar',
    'E:\SteamLibrary\steamapps\common\GodOfWar',
    'F:\SteamLibrary\steamapps\common\GodOfWar',
    'C:\Program Files (x86)\Steam\steamapps\common\GodOfWar',
    'C:\Program Files\Steam\steamapps\common\GodOfWar'
)
$game = $gameCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Container } | Select-Object -First 1
if (-not $game) {
    "No God of War install found in known Steam library locations." | Add-Content -LiteralPath $log -Encoding utf8
    Push-LogOnly 'locate-game'
    Write-Host 'DONE'
    exit 0
}
"game=$game" | Add-Content -LiteralPath $log -Encoding utf8

$steps = @(
    @{ Label='apply-guarded-alignment'; Command='python tools/v0.10.5/align-all-ravens-catalogue-first.py' },
    @{ Label='raven-runtime-model-tests'; Command='python tools/v0.10.5/test_raven_runtime_model.py' },
    @{ Label='all-ravens-lua-tests'; Command='python tools/v0.10.5/test_all_ravens_lua.py' },
    @{ Label='build-release-candidate'; Command=('python tools/v0.10.5/build-all-ravens-release-candidate.py --source-root "' + $game + '"') },
    @{ Label='all-ravens-build-tests'; Command='python tools/v0.10.5/test_all_ravens_build.py' },
    @{ Label='verify-deterministic-rebuild'; Command=('python tools/v0.10.5/build-all-ravens-release-candidate.py --source-root "' + $game + '" --check') },
    @{ Label='fake-game-transaction-tests'; Command='pwsh -NoProfile -ExecutionPolicy Bypass -File tools/v0.10.5/test-all-ravens-transaction.ps1' },
    @{ Label='git-diff-check'; Command='git diff --check' }
)

foreach ($step in $steps) {
    $code = Invoke-Logged -Label $step.Label -Command $step.Command
    if ($code -ne 0) {
        Push-LogOnly $step.Label
        Write-Host 'DONE'
        exit 0
    }
}

"`n=== STATUS BEFORE COMMIT ===" | Add-Content -LiteralPath $log -Encoding utf8
(& $env:ComSpec /d /s /c "git status --short") | Add-Content -LiteralPath $log -Encoding utf8

"`n=== RESULT ===" | Add-Content -LiteralPath $log -Encoding utf8
"RESULT=PASS" | Add-Content -LiteralPath $log -Encoding utf8
"FRESH_SAVE_EXPECTATION=all catalogue Ravens visible by realm" | Add-Content -LiteralPath $log -Encoding utf8
"LIVE_KILL_EXPECTATION=exact killed Raven hidden by native ravenKilled event" | Add-Content -LiteralPath $log -Encoding utf8
"PERSISTED_KILL_BOOTSTRAP_API=tested; automatic save feed still pending" | Add-Content -LiteralPath $log -Encoding utf8

$paths = @(
    'tools/v0.10.5/build-all-ravens-release-candidate.py',
    'tools/v0.10.5/test_all_ravens_build.py',
    'tools/v0.10.5/test_all_ravens_lua.py',
    'tools/v0.10.5/test-all-ravens-transaction.ps1',
    'archive/all-ravens/all-ravens-release-candidate-offline.json',
    'archive/all-ravens/all-ravens-transaction-self-test.json',
    $logRel
)
$quoted = ($paths | ForEach-Object { '"' + $_ + '"' }) -join ' '
& $env:ComSpec /d /s /c "git add -- $quoted >nul 2>&1"
if ($LASTEXITCODE -ne 0) {
    Push-LogOnly 'git-add-results'
    Write-Host 'DONE'
    exit 0
}

& $env:ComSpec /d /s /c "git commit -m ""runtime: open all-Ravens catalogue-first test gate"" >nul 2>&1"
if ($LASTEXITCODE -ne 0) {
    Push-LogOnly 'git-commit-results'
    Write-Host 'DONE'
    exit 0
}

& $env:ComSpec /d /s /c "git push origin $branch >nul 2>&1"
if ($LASTEXITCODE -ne 0) {
    # Commit is safely local. Record a small local marker without printing noisy output.
    "push_failed_after_commit=true" | Set-Content -LiteralPath (Join-Path $env:TEMP 'gow-all-ravens-last-error.txt') -Encoding utf8
}

Write-Host 'DONE'
