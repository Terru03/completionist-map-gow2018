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
$V3ProofRel = 'archive/field-logs/completionist-v104-raven-uid-compass-lifecycle-v3-offline.json'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogRel = "archive/field-logs/runtime-captures/v31-handoff-$Stamp"
$TempLogDir = Join-Path $env:TEMP "completionist-v31-handoff-$Stamp"
$ConsoleLog = Join-Path $TempLogDir 'console-log.txt'
$Summary = Join-Path $TempLogDir 'result.txt'

New-Item -ItemType Directory -Path $TempLogDir -Force | Out-Null
$Succeeded = $false
$FailureText = ''
$PreservedStash = ''

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

function Preserve-V3ProofEdit {
    $proofStatus = @(& git status --porcelain -- $V3ProofRel)
    if ($proofStatus.Count -eq 0) { return }

    Write-Log ''
    Write-Log '=== PRESERVE LOCAL V3 PROOF EDIT ==='

    $stashMessage = "preserve-local-v3-proof-before-v31-handoff-$Stamp"
    $stashBefore = (& git rev-parse -q --verify refs/stash 2>$null)
    if ($null -ne $stashBefore) { $stashBefore = $stashBefore.Trim() }

    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $stashLines = & git stash push -m $stashMessage -- $V3ProofRel 2>&1 |
            ForEach-Object { $_.ToString() }
        $stashCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
    foreach ($line in $stashLines) { Write-Log $line }

    $stashAfter = (& git rev-parse -q --verify refs/stash 2>$null)
    if ($null -ne $stashAfter) { $stashAfter = $stashAfter.Trim() }
    $createdNewStash = -not [string]::IsNullOrWhiteSpace($stashAfter) -and $stashAfter -ne $stashBefore
    $stashContainsProof = $false

    if ($createdNewStash) {
        $stashFiles = @(& git stash show --name-only --format= 'stash@{0}' --)
        if ($LASTEXITCODE -eq 0) {
            $stashContainsProof = @($stashFiles | Where-Object { $_.Trim() -eq $V3ProofRel }).Count -gt 0
        }
    }

    if (-not $createdNewStash -or -not $stashContainsProof) {
        throw "Could not prove that the local v3 proof edit was preserved in a new stash (git stash exit $stashCode)."
    }

    $PreservedStash = (& git stash list -1 --format='%gd %s').Trim()
    Write-Log "preserved_stash=$PreservedStash"

    if ($stashCode -ne 0) {
        Write-Log "git_stash_exit=$stashCode but preservation is verified; continuing with targeted worktree cleanup."
    }

    # Git for Windows can create the stash successfully and still return exit 1
    # while applying its cleanup patch when autocrlf changes line endings. Once we
    # have proven the new stash contains this exact file, restoring only this file
    # is safe and prevents a duplicate-stash/failure loop.
    $proofStillDirty = @(& git status --porcelain -- $V3ProofRel).Count -gt 0
    if ($proofStillDirty) {
        Invoke-Captured 'CLEAN PRESERVED V3 PROOF WORKTREE COPY' {
            & git restore --worktree -- $V3ProofRel
        } | Out-Null
    }

    if (@(& git status --porcelain -- $V3ProofRel).Count -gt 0) {
        throw 'V3 proof edit is preserved in stash but the targeted worktree cleanup did not settle.'
    }
}

try {
    Write-Log 'COMPLETIONIST V3 -> V3.1 RUNTIME HANDOFF'
    Write-Log "time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Log "repo: $Repo"
    Write-Log "game: $GameRoot"
    Write-Log "reviewed_v31_candidate=$V31CandidateCommit"

    $current = (& git branch --show-current).Trim()
    if ($current -ne $V31Branch) {
        throw "Expected starting branch '$V31Branch', got '$current'."
    }

    # Preserve only the known unrelated local proof edit. The verified stash is
    # deliberately left in place after the handoff so it can be reviewed later.
    Preserve-V3ProofEdit
    Assert-TrackedClean

    Invoke-Captured 'SYNC V3.1' { & git pull --ff-only origin $V31Branch } | Out-Null
    Assert-V31CandidateAncestor
    Invoke-Captured 'V3.1 HEAD BEFORE HANDOFF' { & git log -6 --oneline --decorate } | Out-Null

    Invoke-Captured 'SWITCH TO V3' { & git switch $V3Branch } | Out-Null
    Invoke-Captured 'SYNC V3' { & git pull --ff-only origin $V3Branch } | Out-Null
    Assert-TrackedClean

    $v3StatusBefore = Invoke-Captured 'V3 STATUS BEFORE ROLLBACK' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }
    $v3Installed = @($v3StatusBefore | Where-Object { $_ -match '^\s*status:\s*installed\s*$' }).Count -gt 0
    $v3None = @($v3StatusBefore | Where-Object { $_ -match '^\s*active transaction:\s*none\s*$' }).Count -gt 0

    if ($v3Installed) {
        Invoke-Captured 'V3 ROLLBACK' {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3-runtime.ps1' -Mode Rollback -GameRoot $GameRoot
        } | Out-Null
    }
    elseif ($v3None) {
        Write-Log ''
        Write-Log 'V3 already has no active transaction; rollback skipped.'
    }
    else {
        throw 'V3 transaction is in an unexpected state. Refusing to continue.'
    }

    $v3StatusAfter = Invoke-Captured 'V3 STATUS AFTER ROLLBACK' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }
    if (@($v3StatusAfter | Where-Object { $_ -match '^\s*active transaction:\s*none\s*$' }).Count -eq 0) {
        throw 'V3 rollback did not leave active transaction: none.'
    }

    Invoke-Captured 'RETURN TO V3.1' { & git switch $V31Branch } | Out-Null
    Invoke-Captured 'RESYNC V3.1' { & git pull --ff-only origin $V31Branch } | Out-Null
    Assert-V31CandidateAncestor
    Assert-TrackedClean

    Invoke-Captured 'V3.1 OFFLINE GATE' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\verify-raven-uid-compass-lifecycle-v3.1.ps1' -RavenRoot $GameRoot
    } | Out-Null

    $v31StatusBefore = Invoke-Captured 'V3.1 STATUS BEFORE INSTALL' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.1-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }
    $v31Installed = @($v31StatusBefore | Where-Object { $_ -match '^\s*status:\s*installed\s*$' }).Count -gt 0
    $v31None = @($v31StatusBefore | Where-Object { $_ -match '^\s*active transaction:\s*none\s*$' }).Count -gt 0

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
        throw 'V3.1 transaction is in an unexpected pre-install state.'
    }

    $v31StatusAfter = Invoke-Captured 'V3.1 STATUS AFTER INSTALL' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3.1-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }
    if (@($v31StatusAfter | Where-Object { $_ -match '^\s*status:\s*installed\s*$' }).Count -eq 0) {
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
        "preserved_stash=$PreservedStash",
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
        if ($LASTEXITCODE -ne 0) { throw 'Could not stage v3.1 handoff log.' }
        & git diff --cached --quiet
        if ($LASTEXITCODE -ne 0) {
            $message = if ($Succeeded) {
                'Archive Raven lifecycle v3.1 runtime handoff pass'
            } else {
                'Archive Raven lifecycle v3.1 runtime handoff failure'
            }
            & git commit -m $message | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not commit v3.1 handoff log.' }
            & git push origin HEAD | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not push v3.1 handoff log.' }
        }
    }
    catch {
        Write-Warning "Handoff log publication failed: $($_.Exception.Message)"
        Write-Warning "Temporary log remains at: $TempLogDir"
    }
}

if (-not $Succeeded) {
    throw "V3 -> V3.1 handoff failed. Full log was archived under $LogRel when publication succeeded."
}

Write-Host "Done. V3.1 is installed for human runtime testing. Log pushed under $LogRel."
if (-not [string]::IsNullOrWhiteSpace($PreservedStash)) {
    Write-Host "Preserved unrelated local proof edit in stash: $PreservedStash"
}
