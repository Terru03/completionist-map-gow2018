param(
    [ValidateSet('Install','Rollback','Status')]
    [string]$Mode = 'Status',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$ConfirmRuntimeTest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = 'codex/all-collectibles-production-research'
$runner = Join-Path $PSScriptRoot 'all-ravens-runtime-test.ps1'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$archiveDir = Join-Path $repo ("archive\field-logs\runtime\all-ravens-runtime-test-$stamp")
$log = Join-Path $archiveDir 'run.txt'
$manifestCopy = Join-Path $archiveDir 'transaction-manifest.json'
$activeManifest = Join-Path $repo 'build\v0.10.5-all-ravens-runtime-test\transaction\active.json'

New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null

function Append-Line([string]$Text) {
    [IO.File]::AppendAllText($log, $Text + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
}

Append-Line '=== ALL-RAVENS RUNTIME FIELD TEST ==='
Append-Line "timestamp=$stamp"
Append-Line "mode=$Mode"
Append-Line "branch=$branch"
Append-Line "game=$GameRoot"
Append-Line ''

$actionExit = 999
try {
    $currentBranch = (& git -C $repo branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not determine Git branch.' }
    Append-Line "current_branch=$currentBranch"
    if ($currentBranch -ne $branch) { throw "Expected branch '$branch', got '$currentBranch'." }

    $argsList = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $runner,
        '-Mode', $Mode,
        '-GameRoot', $GameRoot
    )
    if ($ConfirmRuntimeTest) { $argsList += '-ConfirmRuntimeTest' }

    Append-Line '=== ACTION OUTPUT ==='
    $output = & pwsh @argsList 2>&1
    $actionExit = $LASTEXITCODE
    foreach ($line in @($output)) { Append-Line ([string]$line) }
    Append-Line "action_exit=$actionExit"
}
catch {
    Append-Line "wrapper_exception=$($_.Exception.Message)"
    $actionExit = 998
}

if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
    try {
        Copy-Item -LiteralPath $activeManifest -Destination $manifestCopy -Force
        Append-Line "manifest_archived=$(Get-SafeRelativePath -Root $repo -Path $manifestCopy -Label 'archived runtime manifest')"
    }
    catch {
        Append-Line "manifest_archive_error=$($_.Exception.Message)"
    }
}

Append-Line ''
Append-Line '=== RESULT ==='
Append-Line "ACTION_EXIT=$actionExit"
if ($actionExit -eq 0) {
    Append-Line 'RESULT=PASS'
}
else {
    Append-Line 'RESULT=FAIL'
}
Append-Line 'OUTPUT_PUSHED_TO_GITHUB=true'

Push-Location $repo
try {
    git add -- $archiveDir | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for runtime archive.' }

    git commit -m "logs: capture all-Ravens runtime $($Mode.ToLowerInvariant()) $stamp" *> $null
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed for runtime archive.' }

    git push origin $branch *> $null
    if ($LASTEXITCODE -ne 0) { throw 'git push failed for runtime archive.' }
}
finally {
    Pop-Location
}

Write-Host 'DONE'
