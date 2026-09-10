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
$V2Branch = 'codex/v104-raven-uid-compass-routing-v2'
$ProofRel = 'archive/field-logs/completionist-v104-raven-uid-compass-routing-v2-offline.json'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogRel = "archive/field-logs/runtime-captures/v3-handoff-$Stamp"
$LogDir = Join-Path $Repo $LogRel
$Transcript = Join-Path $LogDir 'console-transcript.txt'
$Summary = Join-Path $LogDir 'result.txt'
$TempProof = Join-Path $env:TEMP "completionist-v2-proof-$Stamp.json"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$Succeeded = $false
$FailureText = ''
$TranscriptStarted = $false

function Assert-GitSuccess([string]$What) {
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit $LASTEXITCODE)." }
}

function Assert-TrackedClean {
    & git diff --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Tracked working-tree changes exist.' }
    & git diff --cached --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Staged changes exist.' }
}

try {
    Start-Transcript -LiteralPath $Transcript -Force | Out-Null
    $TranscriptStarted = $true

    Write-Host 'COMPLETIONIST V2 ROLLBACK + V3 OFFLINE VERIFY'
    Write-Host "time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Host "repo: $Repo"
    Write-Host "game: $GameRoot"

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $V3Branch) { throw "Expected starting branch '$V3Branch', got '$branch'." }
    Assert-TrackedClean

    Write-Host "`n=== SYNC V3 ==="
    & git pull --ff-only
    Assert-GitSuccess 'V3 pull'

    Write-Host "`n=== V3 HEAD BEFORE RECOVERY ==="
    & git log -5 --oneline --decorate

    # The v2 runtime wrapper requires its archived proof, but that proof was
    # historically untracked on the v2 branch. Preserve the exact copy archived
    # on v3, then place it temporarily into the v2 worktree. Untracked files are
    # intentionally ignored by the transaction engine's tracked-tree guard.
    Write-Host "`n=== EXPORT V2 OFFLINE PROOF FROM V3 ==="
    $proofText = & git show ("$V3Branch`:$ProofRel")
    Assert-GitSuccess 'Exporting v2 proof from v3'
    $proofText | Set-Content -LiteralPath $TempProof -Encoding UTF8

    Write-Host "`n=== CHECKOUT V2 ==="
    & git checkout $V2Branch
    Assert-GitSuccess 'V2 checkout'
    & git pull --ff-only
    Assert-GitSuccess 'V2 pull'
    Assert-TrackedClean

    $ProofPath = Join-Path $Repo $ProofRel
    New-Item -ItemType Directory -Path (Split-Path $ProofPath -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $TempProof -Destination $ProofPath -Force

    Write-Host "`n=== V2 STATUS BEFORE ROLLBACK ==="
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        '.\tools\v0.10.4\raven-uid-compass-routing-runtime.ps1' `
        -Mode Status -GameRoot $GameRoot
    Assert-GitSuccess 'V2 status'

    Write-Host "`n=== V2 ROLLBACK ==="
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        '.\tools\v0.10.4\raven-uid-compass-routing-runtime.ps1' `
        -Mode Rollback -GameRoot $GameRoot
    Assert-GitSuccess 'V2 rollback'

    Write-Host "`n=== V2 STATUS AFTER ROLLBACK ==="
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        '.\tools\v0.10.4\raven-uid-compass-routing-runtime.ps1' `
        -Mode Status -GameRoot $GameRoot
    Assert-GitSuccess 'V2 post-rollback status'

    # Remove the temporary untracked proof before returning to v3, where this path
    # is tracked. Otherwise checkout correctly refuses to overwrite it.
    if (Test-Path -LiteralPath $ProofPath -PathType Leaf) {
        Remove-Item -LiteralPath $ProofPath -Force
    }

    Write-Host "`n=== RETURN TO V3 ==="
    & git checkout $V3Branch
    Assert-GitSuccess 'V3 checkout'
    & git pull --ff-only
    Assert-GitSuccess 'V3 pull after rollback'
    Assert-TrackedClean

    Write-Host "`n=== V3 OFFLINE VERIFICATION ==="
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        '.\tools\v0.10.4\verify-raven-uid-compass-lifecycle-v3.ps1' `
        -RavenRoot $GameRoot
    Assert-GitSuccess 'V3 offline verification'

    Assert-TrackedClean
    $Succeeded = $true
    Write-Host "`nRESULT: PASS"
}
catch {
    $FailureText = ($_ | Out-String).Trim()
    Write-Host "`nRESULT: FAIL"
    Write-Host $FailureText
}
finally {
    # Remove temporary proof before attempting to return to v3.
    try {
        $ProofPath = Join-Path $Repo $ProofRel
        $current = (& git branch --show-current).Trim()
        if ($current -eq $V2Branch -and (Test-Path -LiteralPath $ProofPath -PathType Leaf)) {
            $tracked = (& git ls-files --error-unmatch -- $ProofRel 2>$null)
            if ($LASTEXITCODE -ne 0) { Remove-Item -LiteralPath $ProofPath -Force -ErrorAction SilentlyContinue }
        }
    } catch {}

    Remove-Item -LiteralPath $TempProof -Force -ErrorAction SilentlyContinue

    if ($TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }

    @(
        "result=$(if ($Succeeded) { 'PASS' } else { 'FAIL' })",
        "time_local=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "game_root=$GameRoot",
        "failure=$($FailureText -replace "`r?`n", ' | ')"
    ) | Set-Content -LiteralPath $Summary -Encoding UTF8

    # Always try to return to v3 and publish the log. Logging itself must not
    # alter source/candidate files.
    try {
        Set-Location $Repo
        $current = (& git branch --show-current).Trim()
        if ($current -ne $V3Branch) {
            & git checkout $V3Branch | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not return to v3 for log publication.' }
        }

        & git add -- $LogRel
        if ($LASTEXITCODE -ne 0) { throw 'Could not stage session log.' }

        & git diff --cached --quiet
        $hasLog = $LASTEXITCODE -ne 0
        if ($hasLog) {
            $message = if ($Succeeded) {
                'Archive v2 rollback and v3 offline verification pass'
            } else {
                'Archive v2 rollback and v3 offline verification failure'
            }
            & git commit -m $message | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not commit session log.' }
            & git push origin HEAD | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not push session log.' }
        }
    }
    catch {
        Write-Warning "Session log publication failed: $($_.Exception.Message)"
        Write-Warning "Local log remains at: $Transcript"
    }
}

if (-not $Succeeded) {
    throw "Recovery/verification failed. Full log was archived under $LogRel when publication succeeded."
}

Write-Host "Done. Full log archived under $LogRel and pushed to GitHub."
