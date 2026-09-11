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

$V31Branch = 'codex/v104-raven-uid-compass-lifecycle-v3.1'
$V32Branch = 'codex/v104-raven-uid-compass-lifecycle-v3.2'
$KnownDirtyRel = 'archive/field-logs/completionist-v104-raven-uid-compass-lifecycle-v3.1-offline.json'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogRel = "archive/field-logs/runtime-captures/v32-handoff-$Stamp"
$LogDir = Join-Path $Repo $LogRel
$ConsoleLog = Join-Path $LogDir 'console-log.txt'
$Summary = Join-Path $LogDir 'result.txt'
$DirtyStateLog = Join-Path $LogDir 'preserved-local-state.txt'
$HashLog = Join-Path $LogDir 'installed-file-hashes.txt'
$V31Active = Join-Path $Repo 'build/v0.10.4-raven-uid-compass-lifecycle-v3.1/runtime/transaction/active.json'
$V32Active = Join-Path $Repo 'build/v0.10.4-raven-uid-compass-lifecycle-v3.2/runtime/transaction/active.json'
$DirtyBackup = Join-Path $env:TEMP "completionist-v31-proof-local-$Stamp.bin"

$ApprovedFiles = [ordered]@{
    'mapmaster.dcb' = 'exec/dc/pc_le/mapmaster.dcb'
    'mapcoords.dcb' = 'exec/dc/pc_le/mapcoords.dcb'
    'wad_r_ui.dcb' = 'exec/dc/pc_le/wad_r_ui.dcb'
    'mapmenu.lua' = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
    'precisionchallenge.lua' = 'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua'
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Succeeded = $false
$Published = $false
$FailureText = ''
$PreservedDirty = $false
$RestoredDirty = $false

function Write-Log([string]$Text = '') {
    $Text | Tee-Object -FilePath $ConsoleLog -Append | Out-Host
}

function Invoke-Captured([string]$Label, [scriptblock]$Command) {
    Write-Log ''
    Write-Log "=== $Label ==="

    # Windows PowerShell 5.1 can promote harmless native stderr text (notably
    # Git CRLF warnings) to NativeCommandError under ErrorActionPreference=Stop.
    # Capture native output with Continue and decide success from the exit code.
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

function Invoke-GitQuiet([string]$Label, [scriptblock]$Command, [int[]]$AllowedCodes = @(0)) {
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $lines = & $Command 2>&1 | ForEach-Object { $_.ToString() }
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
    foreach ($line in $lines) { if (-not [string]::IsNullOrWhiteSpace($line)) { Write-Log $line } }
    if ($AllowedCodes -notcontains $code) { throw "$Label failed (exit $code)." }
    return $code
}

function Assert-ExpectedTrackedState {
    $stagedCode = Invoke-GitQuiet 'Checking staged tree' { & git diff --cached --quiet --ignore-submodules -- } @(0,1)
    if ($stagedCode -ne 0) { throw 'Staged changes exist; handoff refused.' }

    # Permit only the already-known v3.1 proof EOL state. Any other tracked
    # working-tree change is outside this helper's authority.
    $otherCode = Invoke-GitQuiet 'Checking unrelated tracked tree' {
        & git diff --quiet --ignore-submodules -- . (":(exclude)$KnownDirtyRel")
    } @(0,1)
    if ($otherCode -ne 0) { throw 'Tracked working-tree changes exist outside the known v3.1 proof path.' }

    $knownCode = Invoke-GitQuiet 'Checking known v3.1 proof state' {
        & git diff --quiet --ignore-submodules -- $KnownDirtyRel
    } @(0,1)

    if ($knownCode -eq 1) {
        $semanticCode = Invoke-GitQuiet 'Verifying known proof differs only at line endings/line-end whitespace' {
            & git diff --quiet --ignore-space-at-eol --ignore-submodules -- $KnownDirtyRel
        } @(0,1)
        if ($semanticCode -ne 0) {
            throw "Known local proof has substantive changes, not only line-ending state: $KnownDirtyRel"
        }
        return $true
    }
    return $false
}

function Assert-FullyTrackedClean {
    $workCode = Invoke-GitQuiet 'Checking tracked working tree' { & git diff --quiet --ignore-submodules -- } @(0,1)
    if ($workCode -ne 0) { throw 'Tracked working-tree changes exist.' }
    $stageCode = Invoke-GitQuiet 'Checking staged tree' { & git diff --cached --quiet --ignore-submodules -- } @(0,1)
    if ($stageCode -ne 0) { throw 'Staged changes exist.' }
}

function Get-StatusFlag([object[]]$Lines, [string]$Pattern) {
    return @($Lines | Where-Object { $_ -match $Pattern }).Count -gt 0
}

function Write-InstalledHashes {
    $rows = @()
    foreach ($name in $ApprovedFiles.Keys) {
        $path = Join-Path $GameRoot ([string]$ApprovedFiles[$name])
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Installed file missing while hashing: $path"
        }
        $sha = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        $rows += "$name=$sha"
    }
    $rows | Set-Content -LiteralPath $HashLog -Encoding UTF8
    foreach ($row in $rows) { Write-Log $row }
}

try {
    Write-Log 'COMPLETIONIST RAVEN V3.1 -> V3.2 RUNTIME HANDOFF'
    Write-Log "time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Log "repo: $Repo"
    Write-Log "game: $GameRoot"
    Write-Log 'game launch requested: false'
    Write-Log 'save/progression writes requested: false'

    $current = (& git branch --show-current).Trim()
    if ($current -ne $V32Branch) { throw "Expected starting branch '$V32Branch', got '$current'." }

    $hasKnownDirty = Assert-ExpectedTrackedState
    @(
        "known_path=$KnownDirtyRel",
        "present_before_handoff=$hasKnownDirty",
        'policy=only line-ending/line-end-whitespace equivalent local state is permitted and preserved'
    ) | Set-Content -LiteralPath $DirtyStateLog -Encoding UTF8

    if ($hasKnownDirty) {
        $knownPath = Join-Path $Repo $KnownDirtyRel
        Copy-Item -LiteralPath $knownPath -Destination $DirtyBackup -Force
        $PreservedDirty = $true
        Invoke-Captured 'TEMPORARILY NORMALIZE KNOWN LOCAL PROOF FOR TRANSACTION GUARDS' {
            & git restore --worktree -- $KnownDirtyRel
        } | Out-Null
        Assert-FullyTrackedClean
        Write-Log "Preserved exact local bytes at temporary backup: $DirtyBackup"
    }

    Invoke-Captured 'SYNC V3.2 BEFORE HANDOFF' { & git pull --ff-only } | Out-Null
    Assert-FullyTrackedClean
    Invoke-Captured 'V3.2 HEAD BEFORE HANDOFF' { & git log -5 --oneline --decorate } | Out-Null

    Write-Log ''
    Write-Log '=== SWITCH TO V3.1 FOR EXACT ROLLBACK ==='
    Invoke-Captured 'CHECKOUT V3.1' { & git checkout $V31Branch } | Out-Null
    Invoke-Captured 'SYNC V3.1' { & git pull --ff-only } | Out-Null
    Assert-FullyTrackedClean

    $v31Before = Invoke-Captured 'V3.1 STATUS BEFORE ROLLBACK' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.1-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }

    $v31Installed = Get-StatusFlag $v31Before '^\s*status:\s*installed\s*$'
    $v31NoActive = Get-StatusFlag $v31Before '^\s*active transaction:\s*none\s*$'
    $v31AlreadyRolled = Get-StatusFlag $v31Before '^\s*status:\s*rolled-back(?:-after-install-failure)?\s*$'

    if ($v31Installed) {
        Invoke-Captured 'V3.1 EXACT TRANSACTION ROLLBACK' {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.1-runtime.ps1' -Mode Rollback -GameRoot $GameRoot
        } | Out-Null
    }
    elseif ($v31NoActive -or $v31AlreadyRolled) {
        Write-Log ''
        Write-Log 'V3.1 has no installed transaction requiring rollback; frozen-byte verification on v3.2 will decide whether handoff may continue.'
    }
    else {
        throw 'V3.1 transaction is in an unexpected state; automatic handoff refused.'
    }

    $v31After = Invoke-Captured 'V3.1 STATUS AFTER ROLLBACK' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.1-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }
    if (Get-StatusFlag $v31After '^\s*status:\s*installed\s*$') {
        throw 'V3.1 still reports installed after rollback.'
    }

    Write-Log ''
    Write-Log '=== RETURN TO V3.2 ==='
    Invoke-Captured 'CHECKOUT V3.2' { & git checkout $V32Branch } | Out-Null
    Invoke-Captured 'SYNC V3.2 AFTER ROLLBACK' { & git pull --ff-only } | Out-Null
    Assert-FullyTrackedClean

    # This verifier hashes the frozen game files, rebuilds the exact candidate,
    # runs the focused regressions and fake-root transaction self-test. It makes
    # no writes to the installed game.
    Invoke-Captured 'V3.2 FROZEN-BASE + OFFLINE HANDOFF VERIFICATION' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\verify-raven-uid-compass-lifecycle-v3.2.ps1' -RavenRoot $GameRoot
    } | Out-Null

    $v32Before = Invoke-Captured 'V3.2 STATUS BEFORE INSTALL' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.2-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }

    if (Get-StatusFlag $v32Before '^\s*status:\s*installed\s*$') {
        throw 'V3.2 unexpectedly already reports installed after v3.1 rollback; handoff refused.'
    }

    Invoke-Captured 'V3.2 TRANSACTIONAL INSTALL FOR HUMAN TEST' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.2-runtime.ps1' -Mode Install -GameRoot $GameRoot -ConfirmRuntimeTest
    } | Out-Null

    $v32After = Invoke-Captured 'V3.2 STATUS AFTER INSTALL' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.2-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }
    if (-not (Get-StatusFlag $v32After '^\s*status:\s*installed\s*$')) {
        throw 'V3.2 status after install does not report installed.'
    }

    Write-Log ''
    Write-Log '=== INSTALLED FILE HASHES ==='
    Write-InstalledHashes

    if (Test-Path -LiteralPath $V31Active -PathType Leaf) {
        Copy-Item -LiteralPath $V31Active -Destination (Join-Path $LogDir 'v31-active-after-handoff.json') -Force
    }
    if (Test-Path -LiteralPath $V32Active -PathType Leaf) {
        Copy-Item -LiteralPath $V32Active -Destination (Join-Path $LogDir 'v32-active-after-install.json') -Force
    }

    $Succeeded = $true
    Write-Log ''
    Write-Log 'RESULT: PASS'
    Write-Log 'V3.1 exact rollback: complete or already unnecessary and frozen-base verified'
    Write-Log 'V3.2 transactional install: installed'
    Write-Log 'God of War launched by helper: false'
}
catch {
    $FailureText = ($_ | Out-String).Trim()
    Write-Log ''
    Write-Log 'RESULT: FAIL'
    Write-Log $FailureText
}
finally {
    @(
        "result=$(if ($Succeeded) { 'PASS' } else { 'FAIL' })",
        "time_local=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "game_root=$GameRoot",
        "v31_branch=$V31Branch",
        "v32_branch=$V32Branch",
        "known_local_state_preserved=$PreservedDirty",
        "game_launched=false",
        "failure=$($FailureText -replace "`r?`n", ' | ')"
    ) | Set-Content -LiteralPath $Summary -Encoding UTF8

    # Return to v3.2 and publish the complete pass/fail record before restoring
    # the user's known line-ending-only local state.
    try {
        Set-Location $Repo
        $current = (& git branch --show-current).Trim()
        if ($current -ne $V32Branch) {
            Invoke-Captured 'RETURN TO V3.2 FOR LOG PUBLICATION' { & git checkout $V32Branch } | Out-Null
        }

        # The preserved local state is still normalized here, so only the new
        # capture directory may be staged/committed.
        Assert-FullyTrackedClean
        Invoke-Captured 'STAGE HANDOFF LOG ONLY' { & git add -- $LogRel } | Out-Null

        $cachedCode = Invoke-GitQuiet 'Checking staged handoff log' { & git diff --cached --quiet -- } @(0,1)
        if ($cachedCode -eq 1) {
            $message = if ($Succeeded) {
                'Archive Raven lifecycle v3.2 runtime handoff pass'
            } else {
                'Archive Raven lifecycle v3.2 runtime handoff failure'
            }
            Invoke-Captured 'COMMIT HANDOFF LOG' { & git commit -m $message } | Out-Null
            Invoke-Captured 'PUSH HANDOFF LOG' { & git push origin HEAD } | Out-Null
        }
        $Published = $true
    }
    catch {
        Write-Warning "Handoff log publication failed: $($_.Exception.Message)"
        Write-Warning "Local log remains at: $ConsoleLog"
    }

    if ($PreservedDirty -and (Test-Path -LiteralPath $DirtyBackup -PathType Leaf)) {
        try {
            Set-Location $Repo
            $current = (& git branch --show-current).Trim()
            if ($current -ne $V32Branch) {
                throw "Cannot restore preserved local proof on unexpected branch '$current'. Exact backup remains at $DirtyBackup"
            }
            Copy-Item -LiteralPath $DirtyBackup -Destination (Join-Path $Repo $KnownDirtyRel) -Force
            $semanticCode = Invoke-GitQuiet 'Verifying restored local proof remains semantically EOL-only' {
                & git diff --quiet --ignore-space-at-eol --ignore-submodules -- $KnownDirtyRel
            } @(0,1)
            if ($semanticCode -ne 0) {
                throw "Restored local proof is no longer semantically equivalent to HEAD; exact backup remains at $DirtyBackup"
            }
            $RestoredDirty = $true
            Remove-Item -LiteralPath $DirtyBackup -Force -ErrorAction SilentlyContinue
            Write-Host "Restored preserved local line-ending state: $KnownDirtyRel"
        }
        catch {
            Write-Warning "Could not restore preserved local state: $($_.Exception.Message)"
            Write-Warning "Exact backup remains at: $DirtyBackup"
        }
    }
}

if (-not $Succeeded) {
    throw "V3.1 -> v3.2 handoff failed. Full log was archived under $LogRel when publication succeeded."
}
if (-not $Published) {
    throw "V3.2 installed, but handoff log publication failed. Local log: $ConsoleLog"
}
if ($PreservedDirty -and -not $RestoredDirty) {
    throw "V3.2 installed and logged, but preserved local proof bytes were not restored. Backup: $DirtyBackup"
}

Write-Host "Done. V3.2 is installed for human runtime testing. Full handoff log pushed under $LogRel."
