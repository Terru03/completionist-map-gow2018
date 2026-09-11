param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Repo = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Repo)) { throw 'Run this from inside the completionist-map-gow2018 repository.' }
Set-Location $Repo

$V32Branch = 'codex/v104-raven-uid-compass-lifecycle-v3.2'
$V33Branch = 'codex/v104-raven-uid-compass-lifecycle-v3.3'
$ReviewedV33 = 'b2116eee65fdaa74e192ed11c25089f3f7fa21b4'
$V32Runtime = 'tools/v0.10.4/raven-uid-compass-lifecycle-v3.2-runtime.ps1'
$V33Runtime = 'tools/v0.10.4/raven-uid-compass-lifecycle-v3.3-runtime.ps1'
$V33Verifier = 'tools/v0.10.4/verify-raven-uid-compass-lifecycle-v3.3.ps1'
$V32ActiveRel = 'build/v0.10.4-raven-uid-compass-lifecycle-v3.2/runtime/transaction/active.json'
$V33ActiveRel = 'build/v0.10.4-raven-uid-compass-lifecycle-v3.3/runtime/transaction/active.json'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogRel = "archive/field-logs/runtime-captures/v33-handoff-$Stamp"
$LogDir = Join-Path $Repo $LogRel
$ConsoleLog = Join-Path $LogDir 'console-log.txt'
$Summary = Join-Path $LogDir 'result.txt'
$LocalStateLog = Join-Path $LogDir 'preserved-local-state.txt'
$HashLog = Join-Path $LogDir 'installed-file-hashes.txt'
$BackupRoot = Join-Path $env:TEMP "completionist-v33-handoff-$Stamp"

$Approved = [ordered]@{
    'exec/dc/pc_le/mapmaster.dcb' = '1e1d5086815bc8553490bff915fea210a8be4f80ce6c88b418b62d7050690a31'
    'exec/dc/pc_le/mapcoords.dcb' = '36bd16f8f21c6387b556e156055ea02f5c262b30a6c450cc0efa05734efb1a0c'
    'exec/dc/pc_le/wad_r_ui.dcb' = '9a434a29ed2e333362e60ac7f224d26855fc9dc86834aa94504a170854e22f2b'
    'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua' = '16e13b342f3bbe98ac9b87eb34bf0115e6b04340d6e41270f38a557f2ed51493'
    'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua' = '61e6bc8efe1fcb9b2a6e796aa86ce9a5f74fc18e97229aae7cc52b652a565800'
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$Succeeded = $false
$FailureText = ''
$Preserved = @()

function Write-Log([string]$Text = '') { $Text | Tee-Object -FilePath $ConsoleLog -Append | Out-Host }

function Invoke-Native([string]$Label, [scriptblock]$Command, [int[]]$AllowedCodes = @(0)) {
    Write-Log ''
    Write-Log "=== $Label ==="
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $lines = & $Command 2>&1 | ForEach-Object { $_.ToString() }
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $old }
    foreach ($line in $lines) { Write-Log $line }
    if ($AllowedCodes -notcontains $code) { throw "$Label failed (exit $code)." }
    return [pscustomobject]@{ Code=$code; Lines=@($lines) }
}

function Assert-NoStaged {
    $r = Invoke-Native 'CHECK STAGED TREE' { & git diff --cached --quiet --ignore-submodules -- } @(0,1)
    if ($r.Code -ne 0) { throw 'Pre-existing staged changes exist; handoff refused.' }
}

function Assert-TrackedClean {
    $r = Invoke-Native 'CHECK TRACKED TREE CLEAN' { & git diff --quiet --ignore-submodules -- } @(0,1)
    if ($r.Code -ne 0) { throw 'Tracked worktree is not clean after temporary preservation.' }
    Assert-NoStaged
}

function Preserve-UnstagedTracked {
    $status = Invoke-Native 'ENUMERATE UNSTAGED TRACKED STATE' { & git diff --name-status --ignore-submodules -- }
    $rows = @($status.Lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($rows.Count -eq 0) {
        'none' | Set-Content -LiteralPath $LocalStateLog -Encoding UTF8
        Write-Log 'preserved_local_state=none'
        return
    }
    foreach ($row in $rows) {
        $parts = $row -split "`t"
        if ($parts.Count -ne 2 -or $parts[0] -ne 'M') { throw "Only ordinary modified tracked files may be auto-preserved; got: $row" }
        $rel = $parts[1]
        $src = Join-Path $Repo $rel
        if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { throw "Modified tracked file missing: $rel" }
        $dst = Join-Path $BackupRoot $rel
        New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $sha = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLowerInvariant()
        $script:Preserved += [pscustomobject]@{ Path=$rel; Backup=$dst; Sha=$sha }
    }
    $Preserved | ForEach-Object { "path=$($_.Path) sha256=$($_.Sha)" } | Set-Content -LiteralPath $LocalStateLog -Encoding UTF8
    Write-Log "preserved_local_state_count=$($Preserved.Count)"
    foreach ($item in $Preserved) {
        Invoke-Native "TEMPORARILY RESTORE TRACKED FILE: $($item.Path)" { & git restore --worktree -- $item.Path } | Out-Null
    }
    Assert-TrackedClean
}

function Restore-PreservedState {
    if ($Preserved.Count -eq 0) { return }
    Write-Log ''
    Write-Log '=== RESTORE EXACT PRE-EXISTING LOCAL BYTES ==='
    foreach ($item in $Preserved) {
        $dst = Join-Path $Repo $item.Path
        New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $item.Backup -Destination $dst -Force
        $actual = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $item.Sha) { throw "Could not restore exact local bytes: $($item.Path)" }
        Write-Log "restored_local_state path=$($item.Path) sha256=$actual"
    }
}

function Get-Flag([object]$Result, [string]$Pattern) { return @($Result.Lines | Where-Object { $_ -match $Pattern }).Count -gt 0 }

function Write-InstalledHashes {
    $rows = @()
    foreach ($relative in $Approved.Keys) {
        $path = Join-Path $GameRoot $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Installed file missing: $relative" }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        $expected = [string]$Approved[$relative]
        if ($actual -ne $expected) { throw "Installed v3.3 hash differs: $relative actual=$actual expected=$expected" }
        $rows += "$relative=$actual"
    }
    $rows | Set-Content -LiteralPath $HashLog -Encoding UTF8
    foreach ($row in $rows) { Write-Log $row }
}

function Publish-Log {
    $current = (& git branch --show-current).Trim()
    if ($current -ne $V33Branch) { throw "Cannot publish from unexpected branch '$current'." }
    & git add -- $LogRel
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage handoff log.' }
    $staged = @(& git diff --cached --name-only --)
    if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate staged paths.' }
    foreach ($path in $staged) { if ($path -notlike "$LogRel/*") { throw "Unexpected staged path: $path" } }
    if ($staged.Count -gt 0) {
        $msg = if ($Succeeded) { 'Archive Raven lifecycle v3.3 runtime handoff' } else { 'Archive Raven lifecycle v3.3 runtime handoff failure' }
        & git commit -m $msg | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Could not commit handoff log.' }
        & git push origin HEAD | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Could not push handoff log.' }
    }
}

try {
    Write-Log 'COMPLETIONIST RAVEN V3.2 -> V3.3 RUNTIME HANDOFF'
    Write-Log "time=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Log "game_root=$GameRoot"
    Write-Log 'game_launch_requested=false'
    Write-Log 'save_progression_marker_writes_requested=false'

    $current = (& git branch --show-current).Trim()
    if ($current -ne $V33Branch) { throw "Expected branch '$V33Branch', got '$current'." }
    Assert-NoStaged
    Preserve-UnstagedTracked

    Invoke-Native 'SYNC V3.3' { & git pull --ff-only } | Out-Null
    Assert-TrackedClean
    Invoke-Native 'VERIFY REVIEWED V3.3 ANCESTOR' { & git merge-base --is-ancestor $ReviewedV33 HEAD } | Out-Null
    Invoke-Native 'V3.3 HEAD' { & git log -5 --oneline --decorate } | Out-Null

    Invoke-Native 'CHECKOUT V3.2 FOR EXACT ROLLBACK' { & git checkout $V32Branch } | Out-Null
    Invoke-Native 'SYNC V3.2' { & git pull --ff-only } | Out-Null
    Assert-TrackedClean
    $v32 = Invoke-Native 'V3.2 STATUS BEFORE ROLLBACK' { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\$V32Runtime" -Mode Status -GameRoot $GameRoot }
    if (Get-Flag $v32 '^\s*status:\s*installed\s*$') {
        Invoke-Native 'V3.2 EXACT TRANSACTION ROLLBACK' { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\$V32Runtime" -Mode Rollback -GameRoot $GameRoot } | Out-Null
    } elseif (-not ((Get-Flag $v32 '^\s*status:\s*rolled-back(?:-after-install-failure)?\s*$') -or (Get-Flag $v32 '^\s*active transaction:\s*none\s*$'))) {
        throw 'V3.2 transaction is in an unexpected state.'
    }
    $v32After = Invoke-Native 'V3.2 STATUS AFTER ROLLBACK' { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\$V32Runtime" -Mode Status -GameRoot $GameRoot }
    if (Get-Flag $v32After '^\s*status:\s*installed\s*$') { throw 'V3.2 still reports installed after rollback.' }
    if (Test-Path -LiteralPath (Join-Path $Repo $V32ActiveRel)) { Copy-Item -LiteralPath (Join-Path $Repo $V32ActiveRel) -Destination (Join-Path $LogDir 'v32-active-after-rollback.json') -Force }

    Invoke-Native 'CHECKOUT V3.3' { & git checkout $V33Branch } | Out-Null
    Invoke-Native 'SYNC V3.3 AFTER ROLLBACK' { & git pull --ff-only } | Out-Null
    Assert-TrackedClean
    Invoke-Native 'V3.3 FROZEN-BASE + OFFLINE VERIFICATION' { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\$V33Verifier" -RavenRoot $GameRoot } | Out-Null

    $v33Before = Invoke-Native 'V3.3 STATUS BEFORE INSTALL' { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\$V33Runtime" -Mode Status -GameRoot $GameRoot }
    if (Get-Flag $v33Before '^\s*status:\s*installed\s*$') { throw 'V3.3 unexpectedly already reports installed.' }

    Invoke-Native 'V3.3 TRANSACTIONAL INSTALL FOR HUMAN TEST' { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\$V33Runtime" -Mode Install -GameRoot $GameRoot -ConfirmRuntimeTest } | Out-Null
    $v33After = Invoke-Native 'V3.3 STATUS AFTER INSTALL' { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\$V33Runtime" -Mode Status -GameRoot $GameRoot }
    if (-not (Get-Flag $v33After '^\s*status:\s*installed\s*$')) { throw 'V3.3 status after install is not installed.' }
    if (Test-Path -LiteralPath (Join-Path $Repo $V33ActiveRel)) { Copy-Item -LiteralPath (Join-Path $Repo $V33ActiveRel) -Destination (Join-Path $LogDir 'v33-active-after-install.json') -Force }

    Write-Log ''
    Write-Log '=== INSTALLED V3.3 HASHES ==='
    Write-InstalledHashes
    $Succeeded = $true
    Write-Log ''
    Write-Log 'RESULT: PASS'
    Write-Log 'v3.2 rollback complete; v3.3 installed; game launched=false'
}
catch {
    $FailureText = ($_ | Out-String).Trim()
    Write-Log ''
    Write-Log 'RESULT: FAIL'
    Write-Log $FailureText
}
finally {
    try {
        $current = (& git branch --show-current).Trim()
        if ($current -ne $V33Branch) {
            Invoke-Native 'RETURN TO V3.3 FOR LOG PUBLICATION' { & git checkout $V33Branch } | Out-Null
        }
        Restore-PreservedState
    } catch {
        $restoreErr = ($_ | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($FailureText)) { $FailureText = $restoreErr } else { $FailureText += " | RESTORE_LOCAL_STATE_FAILED: $restoreErr" }
        $Succeeded = $false
        Write-Log "LOCAL STATE RESTORE FAILURE: $restoreErr"
    }

    @(
        "result=$(if ($Succeeded) { 'PASS' } else { 'FAIL' })",
        "time_local=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "game_root=$GameRoot",
        "preserved_local_state_count=$($Preserved.Count)",
        'helper_game_launch=false',
        'helper_save_progression_marker_writes=false',
        "failure=$($FailureText -replace "`r?`n", ' | ')"
    ) | Set-Content -LiteralPath $Summary -Encoding UTF8

    try { Publish-Log } catch {
        Write-Warning "Handoff log publication failed: $($_.Exception.Message)"
        Write-Warning "Local handoff log remains at: $LogDir"
    }
    Remove-Item -LiteralPath $BackupRoot -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not $Succeeded) { throw "V3.2 -> V3.3 handoff failed. Inspect the pushed $LogRel capture." }
Write-Host "Done. V3.3 is installed for human testing and handoff logs were pushed under $LogRel."
