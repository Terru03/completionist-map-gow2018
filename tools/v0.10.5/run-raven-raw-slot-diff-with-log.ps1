param(
    [string]$FrozenRoot = 'C:\Users\david\Documents\GodOfWar-RavenAliveDead-20260915-220250'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$branch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Run from inside completionist-map-gow2018 repository.' }
Set-Location $repo

$current = (& git branch --show-current).Trim()
if ($current -ne $branch) { throw "Wrong branch. Expected '$branch', found '$current'." }
if (@(& git diff --cached --name-only).Count -gt 0) { throw 'Pre-existing staged changes exist; capture refused.' }

& git pull --ff-only origin $branch | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Branch pull failed.' }

$alivePath = Join-Path $FrozenRoot 'alive\863677734\game.sav'
$deadPath = Join-Path $FrozenRoot 'dead\863677734\game.sav'
foreach ($path in @($alivePath, $deadPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Frozen save missing: $path" }
}

$activeRoot = [System.IO.Path]::GetFullPath((Join-Path $HOME 'Saved Games\God of War'))
foreach ($path in @($alivePath, $deadPath)) {
    $full = [System.IO.Path]::GetFullPath($path)
    if ($full.StartsWith($activeRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing active save path: $full"
    }
}

$prefix = 4160
$stride = 1677512
$aliveSlotIndex = 5
$deadSlotIndex = 17

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/save-captures/gow-raven-raw-slot-diff-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$resultPath = Join-Path $logDir 'result.txt'
$runsCsv = Join-Path $logDir 'changed-runs.csv'
$jsonPath = Join-Path $logDir 'raw-slot-diff.json'
$published = $false
$transcriptStarted = $false
$succeeded = $false

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Publish-Capture {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage capture directory.' }
    $staged = @(& git diff --cached --name-only --)
    foreach ($path in $staged) {
        if ($path -notlike "$relativeLogDir/*") { throw "Unexpected staged path outside capture: $path" }
    }
    if ($staged.Count -gt 0) {
        $message = if ($script:succeeded) { 'Archive Raven raw slot differential' } else { 'Archive Raven raw slot differential failure' }
        & git commit -m $message -- $relativeLogDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Capture commit failed.' }
        & git push origin "HEAD:$branch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Capture push failed.' }
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Raven ALIVE slot 5 vs DEAD slot 17 raw-byte differential ==='
    Write-Host 'Offline frozen-save analysis only. No active save or process access.'

    $aliveBytes = [System.IO.File]::ReadAllBytes($alivePath)
    $deadBytes = [System.IO.File]::ReadAllBytes($deadPath)

    $neededAlive = $prefix + (($aliveSlotIndex + 1) * $stride)
    $neededDead = $prefix + (($deadSlotIndex + 1) * $stride)
    if ($aliveBytes.Length -lt $neededAlive) { throw 'Alive save is too small for requested slot.' }
    if ($deadBytes.Length -lt $neededDead) { throw 'Dead save is too small for requested slot.' }

    $aliveSlot = New-Object byte[] $stride
    $deadSlot = New-Object byte[] $stride
    [Array]::Copy($aliveBytes, $prefix + ($aliveSlotIndex * $stride), $aliveSlot, 0, $stride)
    [Array]::Copy($deadBytes, $prefix + ($deadSlotIndex * $stride), $deadSlot, 0, $stride)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $aliveHash = ([BitConverter]::ToString($sha.ComputeHash($aliveSlot))).Replace('-','').ToLowerInvariant()
        $deadHash = ([BitConverter]::ToString($sha.ComputeHash($deadSlot))).Replace('-','').ToLowerInvariant()
    }
    finally { $sha.Dispose() }

    $changed = New-Object 'System.Collections.Generic.List[int]'
    for ($i = 0; $i -lt $stride; $i++) {
        if ($aliveSlot[$i] -ne $deadSlot[$i]) { [void]$changed.Add($i) }
    }

    $runs = @()
    if ($changed.Count -gt 0) {
        $start = $changed[0]
        $prev = $changed[0]
        for ($j = 1; $j -lt $changed.Count; $j++) {
            $cur = $changed[$j]
            if ($cur -ne ($prev + 1)) {
                $runs += [PSCustomObject]@{ Start = $start; End = $prev; Length = ($prev - $start + 1) }
                $start = $cur
            }
            $prev = $cur
        }
        $runs += [PSCustomObject]@{ Start = $start; End = $prev; Length = ($prev - $start + 1) }
    }

    $runs | Export-Csv -LiteralPath $runsCsv -NoTypeInformation -Encoding UTF8

    $report = [ordered]@{
        analysis = 'raven_alive_dead_raw_slot_diff'
        frozen_root = $FrozenRoot
        alive_path = $alivePath
        dead_path = $deadPath
        prefix = $prefix
        stride = $stride
        alive_slot = $aliveSlotIndex
        dead_slot = $deadSlotIndex
        alive_slot_sha256 = $aliveHash
        dead_slot_sha256 = $deadHash
        raw_slots_identical = ($changed.Count -eq 0)
        changed_byte_count = $changed.Count
        first_changed_offset = if ($changed.Count -gt 0) { $changed[0] } else { $null }
        last_changed_offset = if ($changed.Count -gt 0) { $changed[$changed.Count - 1] } else { $null }
        changed_run_count = $runs.Count
        changed_runs = $runs
        safety = [ordered]@{
            active_save_opened = $false
            process_memory_read = $false
            source_files_written = $false
            raw_save_bytes_archived = $false
        }
    }
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

    @(
        'RAVEN_RAW_SLOT_DIFF_COMPLETED'
        "alive_slot=$aliveSlotIndex"
        "dead_slot=$deadSlotIndex"
        "alive_slot_sha256=$aliveHash"
        "dead_slot_sha256=$deadHash"
        "raw_slots_identical=$($changed.Count -eq 0)"
        "changed_byte_count=$($changed.Count)"
        $(if ($changed.Count -gt 0) { "first_changed_offset=$($changed[0])" } else { 'first_changed_offset=' })
        $(if ($changed.Count -gt 0) { "last_changed_offset=$($changed[$changed.Count - 1])" } else { 'last_changed_offset=' })
        "changed_run_count=$($runs.Count)"
        'active_save_opened=false'
        'process_memory_read=false'
        'raw_save_bytes_archived=false'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8

    Get-Content -LiteralPath $resultPath | ForEach-Object { Write-Host $_ }
    $succeeded = $true
    Publish-Capture
    Write-Host 'RAVEN_RAW_SLOT_DIFF_ARCHIVED' -ForegroundColor Green
}
catch {
    $failure = $_.Exception.ToString()
    $failure | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8
    @(
        'result=FAILED'
        "timestamp=$(Get-Date -Format o)"
        "failure=$($failure -replace "`r?`n", ' | ')"
        'active_save_opened=false'
        'process_memory_read=false'
        'raw_save_bytes_archived=false'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Host "RAVEN_RAW_SLOT_DIFF_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Capture } catch { Write-Host "CAPTURE_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    Stop-LocalTranscript
}
