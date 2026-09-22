[CmdletBinding()]
param(
    [string]$ExpectedBranch = 'codex/collectible-legendary-chests',
    [string]$BeforeDir = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    throw 'Not inside the Completionist Map repository.'
}
Set-Location $RepoRoot

$branch = (& git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    throw "Wrong branch '$branch'; expected '$ExpectedBranch'."
}
if (@(& git diff --cached --name-only).Count -gt 0) {
    throw 'Pre-existing staged changes exist; capture refused.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

$Capture = Join-Path $RepoRoot 'tools\v0.10.5\capture-legendary-current-states-readonly.py'
$Compare = Join-Path $RepoRoot 'tools\v0.10.5\compare-legendary-open-state-transition.py'
$Catalogue = Join-Path $RepoRoot 'config\collectibles\v0.10.5\all-collectibles.json'
$RavenGuard = Join-Path $RepoRoot 'tools\v0.10.5\test-raven-frozen-baseline.ps1'

foreach ($path in @($Capture, $Compare, $Catalogue, $RavenGuard)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}

& pwsh -NoProfile -ExecutionPolicy Bypass -File $RavenGuard
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven baseline guard failed.' }

if ([string]::IsNullOrWhiteSpace($BeforeDir)) {
    $root = Join-Path $RepoRoot 'archive\field-logs\runtime-captures'
    $candidates = @(
        Get-ChildItem -LiteralPath $root -Directory -Filter 'legendary-open-state-before-*' |
            Sort-Object Name -Descending
    )
    $selected = $null
    foreach ($candidate in $candidates) {
        $result = Join-Path $candidate.FullName 'result.txt'
        $report = Join-Path $candidate.FullName 'report.json'
        if (-not (Test-Path -LiteralPath $result -PathType Leaf) -or
            -not (Test-Path -LiteralPath $report -PathType Leaf)) {
            continue
        }
        $text = Get-Content -LiteralPath $result -Raw
        if ($text -match 'result=LEGENDARY_OPEN_STATE_BEFORE_CAPTURED') {
            $selected = $candidate.FullName
            break
        }
    }
    if ($null -eq $selected) {
        throw 'No successful Legendary BEFORE capture was found.'
    }
    $BeforeDir = $selected
}
else {
    $BeforeDir = [IO.Path]::GetFullPath($BeforeDir)
}

$beforeReport = Join-Path $BeforeDir 'report.json'
if (-not (Test-Path -LiteralPath $beforeReport -PathType Leaf)) {
    throw "Missing BEFORE report: $beforeReport"
}

$gow = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') })
if ($gow.Count -ne 1) {
    throw 'Start God of War, remain in the same area after opening exactly one Legendary Chest, let autosave finish, then pause.'
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/legendary-open-state-after-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$console = Join-Path $outDir 'console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
$transitionJson = Join-Path $outDir 'transition-report.json'
$transitionText = Join-Path $outDir 'transition-report.txt'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$exitCode = 0
$failureMessage = ''
Start-Transcript -LiteralPath $console -Force | Out-Null
try {
    Write-Host 'LEGENDARY OPEN-STATE AFTER CAPTURE - READ ONLY'
    Write-Host "Before evidence: $BeforeDir"
    Write-Host 'Assumption: exactly one previously unopened tracked Legendary Chest was opened normally between captures.'
    Write-Host ''

    & $python.Source $Capture --catalogue $Catalogue --output-dir $outDir
    $captureExit = $LASTEXITCODE
    if ($captureExit -ne 0) {
        throw "Legendary AFTER current-state capture failed with exit code $captureExit."
    }

    $afterReport = Join-Path $outDir 'report.json'
    & $python.Source $Compare --before $beforeReport --after $afterReport --output-json $transitionJson --output-text $transitionText
    $compareExit = $LASTEXITCODE
    if ($compareExit -ne 0) {
        throw "Legendary open-state comparison did not find exactly one transition; comparator exit code $compareExit."
    }

    $transition = Get-Content -LiteralPath $transitionJson -Raw | ConvertFrom-Json
    if ($transition.status -ne 'EXACT_ONE_LEGENDARY_STATE_TRANSITION' -or
        -not [bool]$transition.opened_state_semantics_proven -or
        [int]$transition.changed_state_count -ne 1) {
        throw 'Controlled Legendary OPENED-state acceptance contract was not met.'
    }
    if ([bool]$transition.safety.save_written_by_tooling -or
        [bool]$transition.safety.progression_written_by_tooling -or
        [bool]$transition.safety.game_files_written -or
        [bool]$transition.safety.raven_runtime_modified) {
        throw 'Comparator safety contract changed.'
    }

    @(
        'result=LEGENDARY_OPEN_STATE_TRANSITION_PASSED'
        'phase=after'
        "before_dir=$BeforeDir"
        "catalogue_id=$($transition.transition.catalogue_id)"
        "before_state_raw_hex=$($transition.transition.before_state_raw_hex)"
        "before_state_u32=$($transition.transition.before_state_u32)"
        "before_state_float32=$($transition.transition.before_state_float32)"
        "opened_state_raw_hex=$($transition.opened_state.state_raw_hex)"
        "opened_state_u32=$($transition.opened_state.state_u32)"
        "opened_state_float32=$($transition.opened_state.state_float32)"
        'opened_state_semantics_proven=true'
        'save_written_by_tooling=false'
        'progression_written_by_tooling=false'
        'game_files_written=false'
        'raven_runtime_modified=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
catch {
    $exitCode = 1
    $failureMessage = $_.Exception.Message
    @(
        'result=LEGENDARY_OPEN_STATE_TRANSITION_FAILED'
        "before_dir=$BeforeDir"
        "reason=$failureMessage"
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
finally {
    Stop-Transcript | Out-Null
}

& git add -f -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git add after evidence failed' }

$message = if ($exitCode -eq 0) {
    "research(v0.10.5): prove Legendary OPENED state transition $stamp"
} else {
    "research(v0.10.5): archive Legendary OPENED state transition failure $stamp"
}
& git commit -m $message -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git commit after evidence failed' }
& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push after evidence failed' }
$head = (& git rev-parse HEAD).Trim()

if ($exitCode -ne 0) {
    throw "Legendary OPENED-state transition failed; evidence pushed in $head. $failureMessage"
}

Write-Host ''
Write-Host "LEGENDARY_OPEN_STATE_TRANSITION_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
Write-Host "OPENED state raw: $($transition.opened_state.state_raw_hex)" -ForegroundColor Green
Write-Host "OPENED state u32: $($transition.opened_state.state_u32)" -ForegroundColor Green
Write-Host "OPENED state float32: $($transition.opened_state.state_float32)" -ForegroundColor Green
