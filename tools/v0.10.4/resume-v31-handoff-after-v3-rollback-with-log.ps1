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

$V3Branch = 'codex/v104-raven-uid-compass-lifecycle-v3'
$V31Branch = 'codex/v104-raven-uid-compass-lifecycle-v3.1'
$V31CandidateCommit = 'e2b3bb3fe66451539fec60727faf7a517a8fe27b'
$V31ProofRel = 'archive/field-logs/completionist-v104-raven-uid-compass-lifecycle-v3.1-offline.json'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogRel = "archive/field-logs/runtime-captures/v31-resume-$Stamp"
$TempLogDir = Join-Path $env:TEMP "completionist-v31-resume-$Stamp"
$ConsoleLog = Join-Path $TempLogDir 'console-log.txt'
$Summary = Join-Path $TempLogDir 'result.txt'

New-Item -ItemType Directory -Path $TempLogDir -Force | Out-Null
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

function Assert-TrackedClean {
    & git diff --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Tracked working-tree changes remain.' }
    & git diff --cached --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Staged changes remain.' }
}

function Assert-V31CandidateAncestor {
    & git merge-base --is-ancestor $V31CandidateCommit HEAD
    if ($LASTEXITCODE -ne 0) {
        throw "Current v3.1 HEAD does not contain reviewed candidate $V31CandidateCommit."
    }
}

function Has-Line($Lines, [string]$Pattern) {
    return @($Lines | Where-Object { $_ -match $Pattern }).Count -gt 0
}

function Restore-KnownGeneratedV31ProofIfDirty {
    $dirty = @(& git status --porcelain -- $V31ProofRel)
    if ($dirty.Count -eq 0) { return }
    Write-Log ''
    Write-Log '=== RESTORE GENERATED V3.1 PROOF AFTER FAILED GATE ==='
    Write-Log "restoring_known_generated_file=$V31ProofRel"
    Invoke-Captured 'RESTORE V3.1 OFFLINE PROOF TO HEAD' {
        & git restore --worktree -- $V31ProofRel
    } | Out-Null
    if (@(& git status --porcelain -- $V31ProofRel).Count -gt 0) {
        throw 'Known generated v3.1 proof remained dirty after targeted restore.'
    }
}

try {
    Write-Log 'COMPLETIONIST V3.1 HANDOFF RESUME AFTER V3 ROLLBACK'
    Write-Log "time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Log "repo: $Repo"
    Write-Log "game: $GameRoot"
    Write-Log "reviewed_v31_candidate=$V31CandidateCommit"

    $current = (& git branch --show-current).Trim()
    if ($current -ne $V31Branch) {
        throw "Expected starting branch '$V31Branch', got '$current'."
    }

    # The prior failed offline gate may have regenerated this tracked proof before
    # the pin mismatch stopped the run. It is generated output, not user-authored
    # work, so restore only this exact file before enforcing a clean tree.
    Restore-KnownGeneratedV31ProofIfDirty
    Assert-TrackedClean

    Invoke-Captured 'SYNC V3.1' { & git pull --ff-only origin $V31Branch } | Out-Null
    Assert-V31CandidateAncestor
    Invoke-Captured 'V3.1 HEAD BEFORE RESUME' { & git log -10 --oneline --decorate } | Out-Null

    # Re-check v3 only to prove the prior rollback really reached a safe terminal
    # state. A completed transaction may remain recorded as status: rolled-back;
    # that is expected and must not be mistaken for an active install.
    Invoke-Captured 'SWITCH TO V3 FOR ROLLBACK VERIFICATION' { & git switch $V3Branch } | Out-Null
    Invoke-Captured 'SYNC V3' { & git pull --ff-only origin $V3Branch } | Out-Null
    Assert-TrackedClean

    $v3Status = Invoke-Captured 'V3 STATUS - EXPECT ROLLED BACK' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }
    $v3RolledBack = Has-Line $v3Status '^\s*status:\s*rolled-back\s*$'
    $v3None = Has-Line $v3Status '^\s*active transaction:\s*none\s*$'
    $v3Installed = Has-Line $v3Status '^\s*status:\s*installed\s*$'

    if ($v3Installed) {
        throw 'V3 unexpectedly reports installed after the prior successful rollback. Refusing to continue.'
    }
    if (-not $v3RolledBack -and -not $v3None) {
        throw 'V3 is not in a recognized safe post-rollback state.'
    }
    Write-Log "v3_safe_postrollback=true rolled_back=$v3RolledBack no_transaction=$v3None"

    Invoke-Captured 'RETURN TO V3.1' { & git switch $V31Branch } | Out-Null
    Invoke-Captured 'RESYNC V3.1' { & git pull --ff-only origin $V31Branch } | Out-Null
    Assert-V31CandidateAncestor
    Restore-KnownGeneratedV31ProofIfDirty
    Assert-TrackedClean

    Invoke-Captured 'V3.1 OFFLINE GATE' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\verify-raven-uid-compass-lifecycle-v3.1.ps1' -RavenRoot $GameRoot
    } | Out-Null

    $v31StatusBefore = Invoke-Captured 'V3.1 STATUS BEFORE INSTALL' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.1-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }
    $v31Installed = Has-Line $v31StatusBefore '^\s*status:\s*installed\s*$'
    $v31None = Has-Line $v31StatusBefore '^\s*active transaction:\s*none\s*$'

    if ($v31Installed) {
        Write-Log ''
        Write-Log 'V3.1 is already installed; duplicate install skipped.'
    }
    elseif ($v31None) {
        Invoke-Captured 'V3.1 INSTALL' {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.1-runtime.ps1' -Mode Install -GameRoot $GameRoot -ConfirmRuntimeTest
        } | Out-Null
    }
    else {
        throw 'V3.1 transaction is in an unexpected pre-install state. Refusing to continue.'
    }

    $v31StatusAfter = Invoke-Captured 'V3.1 STATUS AFTER INSTALL' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.1-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }
    if (-not (Has-Line $v31StatusAfter '^\s*status:\s*installed\s*$')) {
        throw 'V3.1 status after install does not report installed.'
    }

    $Succeeded = $true
    Write-Log ''
    Write-Log 'RESULT: PASS'
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
        "reviewed_v31_candidate=$V31CandidateCommit",
        "failure=$($FailureText -replace "`r?`n", ' | ')"
    ) | Set-Content -LiteralPath $Summary -Encoding UTF8

    try {
        Set-Location $Repo
        $current = (& git branch --show-current).Trim()
        if ($current -ne $V31Branch) {
            & git switch $V31Branch | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not return to v3.1 for log publication.' }
        }

        $PublishDir = Join-Path $Repo $LogRel
        New-Item -ItemType Directory -Path $PublishDir -Force | Out-Null
        Copy-Item -LiteralPath $ConsoleLog -Destination (Join-Path $PublishDir 'console-log.txt') -Force
        Copy-Item -LiteralPath $Summary -Destination (Join-Path $PublishDir 'result.txt') -Force

        & git add -- $LogRel
        if ($LASTEXITCODE -ne 0) { throw 'Could not stage v3.1 resume log.' }
        & git diff --cached --quiet
        if ($LASTEXITCODE -ne 0) {
            $message = if ($Succeeded) {
                'Archive Raven lifecycle v3.1 runtime resume pass'
            } else {
                'Archive Raven lifecycle v3.1 runtime resume failure'
            }
            & git commit -m $message | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not commit v3.1 resume log.' }
            & git push origin HEAD | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not push v3.1 resume log.' }
        }
    }
    catch {
        Write-Warning "Resume log publication failed: $($_.Exception.Message)"
        Write-Warning "Temporary log remains at: $TempLogDir"
    }
}

if (-not $Succeeded) {
    throw "V3.1 handoff resume failed. Full log was archived under $LogRel when publication succeeded."
}

Write-Host "Done. V3.1 is installed for human runtime testing. Log pushed under $LogRel."
