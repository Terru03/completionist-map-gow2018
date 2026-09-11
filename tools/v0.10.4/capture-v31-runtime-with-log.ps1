param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Repo = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Repo)) {
    throw 'Run this from inside the completionist-map-gow2018 repository.'
}
Set-Location $Repo

$Branch = 'codex/v104-raven-uid-compass-lifecycle-v3.1'
$ReviewedCandidate = 'e2b3bb3fe66451539fec60727faf7a517a8fe27b'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogRel = "archive/field-logs/runtime-captures/v31-runtime-$Stamp"
$LogDir = Join-Path $Repo $LogRel
$ConsoleLog = Join-Path $LogDir 'console-log.txt'
$Summary = Join-Path $LogDir 'result.txt'
$Observation = Join-Path $LogDir 'human-observation.txt'
$LoaderLog = Join-Path $GameRoot 'mods\loader_log.txt'
$LoaderCopy = Join-Path $LogDir 'loader_log.txt'
$LoaderExtract = Join-Path $LogDir 'completionist-loader-extract.txt'
$EventsFile = Join-Path $LogDir 'windows-events.txt'

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Succeeded = $false
$FailureText = ''

function Write-Log([string]$Text = '') {
    $Text | Tee-Object -FilePath $ConsoleLog -Append | Out-Host
}

function Invoke-Captured([string]$Label, [scriptblock]$Command) {
    Write-Log ''
    Write-Log "=== $Label ==="
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $lines = & $Command 2>&1 | ForEach-Object { $_.ToString() }
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
    foreach ($line in $lines) { Write-Log $line }
    if ($code -ne 0) { throw "$Label failed (exit $code)." }
    return ,$lines
}

function Ask([string]$Key, [string]$Prompt) {
    $answer = Read-Host "$Prompt [Y/N/NA]"
    "$Key=$answer" | Add-Content -LiteralPath $Observation -Encoding UTF8
}

try {
    Write-Log 'COMPLETIONIST RAVEN UID LIFECYCLE V3.1 RUNTIME CAPTURE'
    Write-Log "time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Log "repo: $Repo"
    Write-Log "game: $GameRoot"
    Write-Log "reviewed_candidate=$ReviewedCandidate"

    $current = (& git branch --show-current).Trim()
    if ($current -ne $Branch) { throw "Expected branch '$Branch', got '$current'." }

    & git merge-base --is-ancestor $ReviewedCandidate HEAD
    if ($LASTEXITCODE -ne 0) { throw "Current branch no longer contains reviewed candidate $ReviewedCandidate." }

    Invoke-Captured 'V3.1 HEAD' { & git log -8 --oneline --decorate } | Out-Null
    $runtimeStatus = Invoke-Captured 'V3.1 RUNTIME STATUS' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.1-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }
    if (@($runtimeStatus | Where-Object { $_ -match '^\s*status:\s*installed\s*$' }).Count -eq 0) {
        throw 'V3.1 runtime status is not installed. Refusing to record a misleading runtime capture.'
    }

    if (Test-Path -LiteralPath $LoaderLog -PathType Leaf) {
        Copy-Item -LiteralPath $LoaderLog -Destination $LoaderCopy -Force
        $pattern = 'CompletionistMap|uid-lifecycle-v3\.1|shared-loader-twin|CompletionistRaven|SELECT_CAPTURE|SELECT_CONSUME|STOCK_REPLACE_TWIN|REAL_HIDE|CLEANUP_SETTLED|LIFECYCLE_REARM|SCHEDULE_FAILED'
        Select-String -LiteralPath $LoaderLog -Pattern $pattern |
            ForEach-Object { $_.Line } |
            Set-Content -LiteralPath $LoaderExtract -Encoding UTF8
        Write-Log "loader_log_copied=true bytes=$((Get-Item -LiteralPath $LoaderCopy).Length)"
    }
    else {
        Write-Log 'loader_log_copied=false'
    }

    $since = (Get-Date).AddHours(-3)
    try {
        Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$since} -ErrorAction Stop |
            Where-Object { $_.Message -match 'GoW\.exe|GodOfWar|GoW' } |
            Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message |
            Format-List | Out-String -Width 300 |
            Set-Content -LiteralPath $EventsFile -Encoding UTF8
    }
    catch {
        "Windows event capture failed: $($_.Exception.Message)" |
            Set-Content -LiteralPath $EventsFile -Encoding UTF8
    }

    @(
        "capture_time=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "reviewed_candidate=$ReviewedCandidate",
        'answers: Y=yes, N=no, NA=not tested'
    ) | Set-Content -LiteralPath $Observation -Encoding UTF8

    Write-Host ''
    Write-Host 'Answer these from the v3.1 runtime test. Use Y, N, or NA.'
    Ask 'initial_real_and_twin_visible' 'Before collection, were both real Raven and Twin map markers visible?'
    Ask 'real_tracks_custom_hud' 'Did real Raven track with the custom Raven compass/HUD icon?'
    Ask 'twin_tracks_custom_hud' 'Did Twin track with the custom Raven compass/HUD icon?'
    Ask 'real_twin_switch_no_duplicates' 'Did repeated real/Twin switching always target the selected marker with no duplicate active targets?'
    Ask 'stock_dock_native' 'Did stock Dock retain native behavior/art?'
    Ask 'stock_to_twin_custom' 'Did switching from stock Dock to Twin produce the correct custom Twin target?'
    Ask 'real_target_clears_map_closed' 'With real Raven tracked and map closed, did killing it clear the stale HUD/in-world target promptly without reopening the map?'
    Ask 'postkill_real_absent_twin_present' 'After reopening map post-kill, was real absent while Twin remained present?'
    Ask 'postkill_twin_selectable_trackable' 'After real Raven collection, was Twin still selectable and trackable?'
    Ask 'twin_survives_real_kill' 'With Twin tracked when real Raven was killed, did Twin HUD remain active and Twin remain/reappear on map?'
    Ask 'stock_survives_real_kill' 'With a stock target active when real Raven was killed, did that stock target remain untouched?'
    Ask 'restore_old_state_real_returns' 'After restoring/loading an older uncollected Raven state, did the real Raven return appropriately?'
    Ask 'recollect_cleanup_rearms' 'After that restore, did recollecting the Raven again clear the real HUD target promptly?'
    Ask 'crash_occurred' 'Did God of War crash during this v3.1 test?'

    $notes = Read-Host 'Optional short notes (press Enter for none)'
    "notes=$notes" | Add-Content -LiteralPath $Observation -Encoding UTF8

    $Succeeded = $true
    Write-Log ''
    Write-Log 'RESULT: CAPTURED'
}
catch {
    $FailureText = ($_ | Out-String).Trim()
    Write-Log ''
    Write-Log 'RESULT: FAIL'
    Write-Log $FailureText
}
finally {
    @(
        "result=$(if ($Succeeded) { 'CAPTURED' } else { 'FAIL' })",
        "time_local=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "game_root=$GameRoot",
        "reviewed_candidate=$ReviewedCandidate",
        "failure=$($FailureText -replace "`r?`n", ' | ')"
    ) | Set-Content -LiteralPath $Summary -Encoding UTF8

    try {
        Set-Location $Repo
        $current = (& git branch --show-current).Trim()
        if ($current -ne $Branch) { throw "Cannot publish runtime capture from unexpected branch '$current'." }
        & git add -- $LogRel
        if ($LASTEXITCODE -ne 0) { throw 'Could not stage runtime capture.' }
        & git diff --cached --quiet
        if ($LASTEXITCODE -ne 0) {
            & git commit -m 'Archive Raven lifecycle v3.1 runtime capture' | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not commit runtime capture.' }
            & git push origin HEAD | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not push runtime capture.' }
        }
    }
    catch {
        Write-Warning "Runtime capture publication failed: $($_.Exception.Message)"
        Write-Warning "Local capture remains at: $LogDir"
    }
}

if (-not $Succeeded) {
    throw "V3.1 runtime capture failed. Logs were archived under $LogRel when publication succeeded."
}

Write-Host "Done. V3.1 runtime logs and human observations pushed under $LogRel."
