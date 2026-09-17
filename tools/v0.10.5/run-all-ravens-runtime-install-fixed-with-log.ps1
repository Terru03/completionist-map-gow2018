param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = 'codex/all-collectibles-production-research'
$sourceRunner = Join-Path $PSScriptRoot 'all-ravens-runtime-test.ps1'
$tempRunner = Join-Path $PSScriptRoot ('.all-ravens-runtime-test-forwarded-' + $PID + '.ps1')
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
Append-Line 'mode=Install'
Append-Line "branch=$branch"
Append-Line "game=$GameRoot"
Append-Line 'mode_forwarding_fix=explicit_library_parameter_forwarding'
Append-Line ''

$actionExit = 999
try {
    $currentBranch = (& git -C $repo branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not determine Git branch.' }
    Append-Line "current_branch=$currentBranch"
    if ($currentBranch -ne $branch) { throw "Expected branch '$branch', got '$currentBranch'." }

    $text = [IO.File]::ReadAllText($sourceRunner)
    $old = '. $engine -LibraryOnly'
    $new = '. $engine -Mode $Mode -GameRoot $GameRoot -ConfirmRuntimeTest:$ConfirmRuntimeTest -LibraryOnly'
    $matches = ([regex]::Matches($text, [regex]::Escape($old))).Count
    if ($matches -ne 1) { throw "Expected exactly one library import line, found $matches." }
    $text = $text.Replace($old, $new)
    [IO.File]::WriteAllText($tempRunner, $text, (New-Object Text.UTF8Encoding($false)))

    Append-Line '=== ACTION OUTPUT ==='
    $output = & pwsh -NoProfile -ExecutionPolicy Bypass -File $tempRunner -Mode Install -GameRoot $GameRoot -ConfirmRuntimeTest 2>&1
    $actionExit = $LASTEXITCODE
    foreach ($line in @($output)) { Append-Line ([string]$line) }
    Append-Line "action_exit=$actionExit"
}
catch {
    Append-Line "wrapper_exception=$($_.Exception.Message)"
    $actionExit = 998
}
finally {
    Remove-Item -LiteralPath $tempRunner -Force -ErrorAction SilentlyContinue
}

if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
    try {
        Copy-Item -LiteralPath $activeManifest -Destination $manifestCopy -Force
        $relativeManifest = [IO.Path]::GetRelativePath($repo, $manifestCopy).Replace('\','/')
        Append-Line "manifest_archived=$relativeManifest"
    }
    catch {
        Append-Line "manifest_archive_error=$($_.Exception.Message)"
    }
}

Append-Line ''
Append-Line '=== RESULT ==='
Append-Line "ACTION_EXIT=$actionExit"
if ($actionExit -eq 0) { Append-Line 'RESULT=PASS' } else { Append-Line 'RESULT=FAIL' }
Append-Line 'OUTPUT_PUSHED_TO_GITHUB=true'

Push-Location $repo
try {
    git add -- $archiveDir | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for runtime archive.' }
    git commit -m "logs: capture fixed all-Ravens runtime install $stamp" *> $null
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed for runtime archive.' }
    git push origin $branch *> $null
    if ($LASTEXITCODE -ne 0) { throw 'git push failed for runtime archive.' }
}
finally {
    Pop-Location
}

Write-Host 'DONE'
