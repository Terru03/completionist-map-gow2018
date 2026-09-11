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

$Branch = 'codex/v104-raven-uid-compass-lifecycle-v3.2'
$ProofRel = 'archive/field-logs/completionist-v104-raven-uid-compass-lifecycle-v3.2-offline.json'
$ActiveRel = 'build/v0.10.4-raven-uid-compass-lifecycle-v3.2/runtime/transaction/active.json'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogRel = "archive/field-logs/runtime-captures/v32-runtime-$Stamp"
$LogDir = Join-Path $Repo $LogRel
$ConsoleLog = Join-Path $LogDir 'console-log.txt'
$Summary = Join-Path $LogDir 'result.txt'
$Observation = Join-Path $LogDir 'human-observation.txt'
$Metadata = Join-Path $LogDir 'capture-metadata.txt'
$HashLog = Join-Path $LogDir 'installed-file-hashes.txt'
$TrackedStateLog = Join-Path $LogDir 'preexisting-unstaged-tracked.txt'
$LoaderLog = Join-Path $GameRoot 'mods\loader_log.txt'
$LoaderCopy = Join-Path $LogDir 'loader_log.txt'
$LoaderExtract = Join-Path $LogDir 'completionist-loader-extract.txt'
$EventsFile = Join-Path $LogDir 'windows-events.txt'
$ActiveCopy = Join-Path $LogDir 'v32-active.json'

$ApprovedFiles = @(
    'exec/dc/pc_le/mapmaster.dcb',
    'exec/dc/pc_le/mapcoords.dcb',
    'exec/dc/pc_le/wad_r_ui.dcb',
    'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua',
    'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua'
)

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Succeeded = $false
$FailureText = ''
$Head = ''
$PreexistingTracked = @()

function Write-Log([string]$Text = '') {
    $Text | Tee-Object -FilePath $ConsoleLog -Append | Out-Host
}

function Invoke-Native([string]$Label, [scriptblock]$Command, [int[]]$AllowedCodes = @(0)) {
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
    if ($AllowedCodes -notcontains $code) { throw "$Label failed (exit $code)." }
    return [pscustomobject]@{ Code = $code; Lines = @($lines) }
}

function Assert-NoPreexistingStagedChanges {
    $staged = Invoke-Native 'CHECK STAGED TREE' { & git diff --cached --quiet --ignore-submodules -- } @(0,1)
    if ($staged.Code -ne 0) {
        throw 'Pre-existing staged changes exist; capture refused so unrelated work cannot enter the capture commit.'
    }
}

function Record-UnstagedTrackedChanges {
    $state = Invoke-Native 'RECORD UNSTAGED TRACKED TREE' { & git diff --name-status --ignore-submodules -- }
    $script:PreexistingTracked = @($state.Lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($script:PreexistingTracked.Count -eq 0) {
        'none' | Set-Content -LiteralPath $TrackedStateLog -Encoding UTF8
        Write-Log 'preexisting_unstaged_tracked_changes=none'
    }
    else {
        $script:PreexistingTracked | Set-Content -LiteralPath $TrackedStateLog -Encoding UTF8
        Write-Log "preexisting_unstaged_tracked_changes=$($script:PreexistingTracked.Count)"
        Write-Log 'Recorded only; these paths are not staged, restored, or modified by this helper.'
    }
}

function Assert-GameClosed {
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') })
    if ($running.Count -gt 0) { throw 'God of War is still running. Exit it completely before capture.' }
}

function Ask([string]$Key, [string]$Prompt) {
    while ($true) {
        $answer = (Read-Host "$Prompt [Y/N/NA]").Trim().ToUpperInvariant()
        if ($answer -in @('Y','N','NA')) {
            "$Key=$answer" | Add-Content -LiteralPath $Observation -Encoding UTF8
            return
        }
        Write-Host 'Please answer Y, N, or NA.'
    }
}

function Get-CanonicalProof([string]$Commit) {
    $spec = "${Commit}:$ProofRel"
    $show = Invoke-Native 'READ CANONICAL V3.2 PROOF FROM GIT HEAD' { & git show $spec }
    $json = ($show.Lines -join "`n")
    if ([string]::IsNullOrWhiteSpace($json)) { throw 'Committed v3.2 proof is empty or unavailable.' }
    $proof = $json | ConvertFrom-Json
    if ($proof.result -ne 'RAVEN_UID_COMPASS_LIFECYCLE_V32_OFFLINE_PROOF_PASSED' -or
        $proof.ready_for_runtime_test -ne $true -or
        $proof.runtime_test_performed -ne $false -or
        $proof.game_files_written -ne $false) {
        throw 'Committed v3.2 proof gate differs from the approved runtime candidate.'
    }
    return $proof
}

function Write-And-VerifyInstalledHashes([object]$Proof) {
    $rows = @()
    foreach ($relative in $ApprovedFiles) {
        $path = Join-Path $GameRoot $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Installed file missing: $relative" }
        $property = $Proof.files.PSObject.Properties[$relative]
        if ($null -eq $property) { throw "Committed proof has no candidate entry for: $relative" }
        $expected = [string]$property.Value.sha256
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) { throw "Installed v3.2 hash differs: $relative actual=$actual expected=$expected" }
        $rows += "$relative=$actual"
    }
    $rows | Set-Content -LiteralPath $HashLog -Encoding UTF8
    foreach ($row in $rows) { Write-Log $row }
}

function Publish-Capture {
    & git add -- $LogRel
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage capture directory.' }

    $staged = @(& git diff --cached --name-only --)
    if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate staged paths.' }
    foreach ($path in $staged) {
        if ($path -notlike "$LogRel/*") { throw "Unexpected staged path outside capture directory: $path" }
    }

    if ($staged.Count -gt 0) {
        $message = if ($Succeeded) { 'Archive Raven lifecycle v3.2 runtime capture' } else { 'Archive Raven lifecycle v3.2 runtime capture failure' }
        & git commit -m $message | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Could not commit runtime capture.' }
        & git push origin HEAD | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Could not push runtime capture.' }
    }
}

try {
    Write-Log 'COMPLETIONIST RAVEN UID LIFECYCLE V3.2 HUMAN RUNTIME CAPTURE V2'
    Write-Log "time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Log "repo: $Repo"
    Write-Log "game: $GameRoot"
    Write-Log 'game files written by capture helper: false'
    Write-Log 'save/progression/marker-state writes by capture helper: false'

    $current = (& git branch --show-current).Trim()
    if ($current -ne $Branch) { throw "Expected branch '$Branch', got '$current'." }

    Assert-NoPreexistingStagedChanges
    Record-UnstagedTrackedChanges
    Assert-GameClosed

    $Head = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Head)) { throw 'Could not resolve repository HEAD.' }
    Write-Log "canonical_proof_commit=$Head"
    $proof = Get-CanonicalProof -Commit $Head

    $activePath = Join-Path $Repo $ActiveRel
    if (-not (Test-Path -LiteralPath $activePath -PathType Leaf)) { throw 'v3.2 active transaction manifest is missing.' }
    $active = Get-Content -LiteralPath $activePath -Raw | ConvertFrom-Json
    if ([string]$active.status -ne 'installed') { throw "v3.2 transaction status is '$($active.status)', expected installed." }
    Copy-Item -LiteralPath $activePath -Destination $ActiveCopy -Force
    Write-Log "transaction_id=$($active.transaction_id)"
    Write-Log "transaction_status=$($active.status)"

    Write-Log ''
    Write-Log '=== INSTALLED V3.2 HASH VERIFICATION AGAINST COMMITTED PROOF ==='
    Write-And-VerifyInstalledHashes -Proof $proof

    @(
        "capture_time_local=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "branch=$Branch",
        "canonical_proof_commit=$Head",
        "transaction_id=$($active.transaction_id)",
        "transaction_status=$($active.status)",
        "preexisting_unstaged_tracked_count=$($PreexistingTracked.Count)",
        'helper_game_writes=false',
        'helper_save_progression_writes=false'
    ) | Set-Content -LiteralPath $Metadata -Encoding UTF8

    if (Test-Path -LiteralPath $LoaderLog -PathType Leaf) {
        Copy-Item -LiteralPath $LoaderLog -Destination $LoaderCopy -Force
        $regex = 'CompletionistMap|uid-lifecycle-v3\.2|uid-lifecycle-v32|SELECT_CANDIDATE|SELECT_ARM|SELECT_CONSUME|SELECT_DISARM|STOCK_REPLACE_TWIN|REAL_HIDE|CLEANUP_SETTLED|LIFECYCLE_REARM|OnHitByWeapon|OnRestoreCheckpoint|OnStart|Completionist_V103_Veithurgard_Raven_01|Completionist_V104_Veithurgard_Raven_Twin_01|3410085282531601808|CompletionistRaven|single-active-v3|ERROR|FATAL|crash'
        Select-String -LiteralPath $LoaderLog -Pattern $regex -CaseSensitive:$false | ForEach-Object { $_.Line } | Set-Content -LiteralPath $LoaderExtract -Encoding UTF8
        Write-Log "loader_log_copied=true bytes=$((Get-Item -LiteralPath $LoaderCopy).Length)"
        Write-Log "loader_log_sha256=$((Get-FileHash -LiteralPath $LoaderCopy -Algorithm SHA256).Hash.ToLowerInvariant())"
    }
    else {
        'loader_log.txt was not present after the human test.' | Set-Content -LiteralPath $LoaderExtract -Encoding UTF8
        Write-Log 'loader_log_copied=false'
    }

    $since = (Get-Date).AddHours(-8)
    try {
        Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$since} -ErrorAction Stop |
            Where-Object { $_.ProviderName -match 'Application Error|Windows Error Reporting' -or $_.Message -match 'GoW\.exe|GodOfWar|GoW' } |
            Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message |
            Format-List | Out-String -Width 320 | Set-Content -LiteralPath $EventsFile -Encoding UTF8
    }
    catch {
        "Windows event capture failed: $($_.Exception.Message)" | Set-Content -LiteralPath $EventsFile -Encoding UTF8
    }

    @(
        "capture_time_local=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        'answers: Y=yes, N=no, NA=not tested/not practical in this run'
    ) | Set-Content -LiteralPath $Observation -Encoding UTF8

    Write-Host ''
    Write-Host 'Answer from the v3.2 game test you already performed. Use Y, N, or NA.'
    Ask 'initial_real_and_twin_visible' 'Before collecting real Raven, were both real and Twin map markers visible?'
    Ask 'real_tracks_correct_custom_target' 'Did clicking REAL track the real marker with the custom Raven HUD/in-world target?'
    Ask 'twin_tracks_correct_custom_target' 'Did clicking TWIN track Twin itself with the custom Raven HUD/in-world target?'
    Ask 'real_twin_real_switch_single_active' 'Did REAL -> TWIN -> REAL keep exactly one active user target?'
    Ask 'same_marker_second_click_removes' 'Did clicking the already-active custom marker again remove the target?'
    Ask 'stock_dock_native' 'Did stock Dock retain native art/behavior?'
    Ask 'twin_to_stock_replacement' 'Did stock correctly replace Twin?'
    Ask 'stock_to_twin_replacement' 'Did Twin correctly replace stock?'
    Ask 'real_kill_map_closed_clears_immediately' 'With REAL tracked and map closed, did killing real clear its HUD/in-world target promptly?'
    Ask 'postkill_real_absent_twin_present' 'After kill, was real absent and Twin still present?'
    Ask 'postkill_twin_selectable' 'After real completion, was Twin still selectable/trackable as Twin?'
    Ask 'twin_tracked_survives_real_kill' 'On pre-kill reload with TWIN tracked, did killing real leave Twin untouched?'
    Ask 'stock_tracked_survives_real_kill' 'On pre-kill reload with STOCK tracked, did killing real leave stock untouched?'
    Ask 'restore_uncollected_real_returns' 'After restoring/loading uncollected state, did real Raven return?'
    Ask 'recollect_after_restore_clears_again' 'After restore, did recollecting real promptly clear its tracked target again?'
    Ask 'crash_occurred' 'Did God of War crash during the v3.2 test?'

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
    $resultText = if ($Succeeded) { 'CAPTURED' } else { 'FAIL' }
    @(
        "result=$resultText",
        "time_local=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "game_root=$GameRoot",
        "canonical_proof_commit=$Head",
        "preexisting_unstaged_tracked_count=$($PreexistingTracked.Count)",
        'helper_game_writes=false',
        'helper_save_progression_writes=false',
        "failure=$($FailureText -replace "`r?`n", ' | ')"
    ) | Set-Content -LiteralPath $Summary -Encoding UTF8

    try { Publish-Capture }
    catch {
        Write-Warning "Runtime capture publication failed: $($_.Exception.Message)"
        Write-Warning "Local capture remains at: $LogDir"
    }
}

if (-not $Succeeded) {
    throw "V3.2 runtime capture failed. Logs were archived under $LogRel when publication succeeded."
}

Write-Host "Done. V3.2 runtime logs and observations archived under $LogRel and pushed to GitHub."
