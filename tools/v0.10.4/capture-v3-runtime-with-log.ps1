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

$Branch = 'codex/v104-raven-uid-compass-lifecycle-v3'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogRel = "archive/field-logs/runtime-captures/v3-runtime-$Stamp"
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
    Write-Log ""
    Write-Log "=== $Label ==="
    $lines = & $Command 2>&1 | ForEach-Object { $_.ToString() }
    $code = $LASTEXITCODE
    foreach ($line in $lines) { Write-Log $line }
    if ($code -ne 0) { throw "$Label failed (exit $code)." }
    return ,$lines
}

function Ask([string]$Key, [string]$Prompt) {
    $answer = Read-Host "$Prompt [Y/N/NA]"
    "$Key=$answer" | Add-Content -LiteralPath $Observation -Encoding UTF8
}

try {
    Write-Log 'COMPLETIONIST RAVEN UID LIFECYCLE V3 RUNTIME CAPTURE'
    Write-Log "time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Log "repo: $Repo"
    Write-Log "game: $GameRoot"

    $current = (& git branch --show-current).Trim()
    if ($current -ne $Branch) { throw "Expected branch '$Branch', got '$current'." }

    Invoke-Captured 'SYNC V3' { & git pull --ff-only }
    Invoke-Captured 'V3 HEAD' { & git log -6 --oneline --decorate }
    Invoke-Captured 'V3 RUNTIME STATUS' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }

    if (Test-Path -LiteralPath $LoaderLog -PathType Leaf) {
        Copy-Item -LiteralPath $LoaderLog -Destination $LoaderCopy -Force
        $pattern = 'CompletionistMap|uid-lifecycle-v3|shared-loader-twin|CompletionistRaven'
        Select-String -LiteralPath $LoaderLog -Pattern $pattern | ForEach-Object { $_.Line } | Set-Content -LiteralPath $LoaderExtract -Encoding UTF8
        Write-Log "loader_log_copied=true bytes=$((Get-Item -LiteralPath $LoaderCopy).Length)"
    }
    else {
        Write-Log 'loader_log_copied=false'
    }

    $since = (Get-Date).AddHours(-2)
    try {
        Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$since} -ErrorAction Stop |
            Where-Object { $_.Message -match 'GoW\.exe|GodOfWar|GoW' } |
            Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message |
            Format-List | Out-String -Width 300 | Set-Content -LiteralPath $EventsFile -Encoding UTF8
    }
    catch {
        "Windows event capture failed: $($_.Exception.Message)" | Set-Content -LiteralPath $EventsFile -Encoding UTF8
    }

    @(
        "capture_time=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        'answers: Y=yes, N=no, NA=not tested'
    ) | Set-Content -LiteralPath $Observation -Encoding UTF8

    Write-Host ''
    Write-Host 'Answer these from the runtime test. Use Y, N, or NA.'
    Ask 'initial_real_and_twin_visible' 'Before collection, were both the real Raven and Twin map markers visible?'
    Ask 'real_tracks_custom_hud' 'Did the real Raven track with the custom Raven compass/HUD icon?'
    Ask 'twin_tracks_custom_hud' 'Did Twin track with the same custom Raven compass/HUD icon?'
    Ask 'stock_dock_native' 'Did stock Dock keep its native behavior/art and replacement still work?'
    Ask 'real_target_clears_immediately_on_kill' 'With REAL Raven tracked, did its HUD/in-world target disappear automatically on kill without opening map or selecting another target?'
    Ask 'postkill_real_absent_twin_present' 'After the real Raven was killed and map reopened, was real absent while Twin remained present/selectable?'
    Ask 'twin_survives_real_kill' 'With TWIN tracked when the real Raven was killed, did Twin stay active and remain/reappear on the map?'
    Ask 'crash_occurred' 'Did God of War crash during this v3 test?'

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
            & git commit -m 'Archive Raven lifecycle v3 runtime capture' | Out-Host
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
    throw "V3 runtime capture failed. Logs were archived under $LogRel when publication succeeded."
}

Write-Host "Done. Runtime logs and human observations pushed under $LogRel."
