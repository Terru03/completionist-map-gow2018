param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-ravens-release-candidate'
$target = 'catalogue/odins-ravens.json'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$branch = (& git branch --show-current).Trim()
if ($branch -ne $expectedBranch) {
    throw "Wrong branch. Expected '$expectedBranch', found '$branch'."
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/all-ravens-dirty-inspect-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$consoleLog = Join-Path $logDir 'console-log.txt'
$transcriptStarted = $false

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map all-Ravens dirty-state inspection ==='
    Write-Host 'Read-only inspection of the pre-existing catalogue worktree edit.'
    Write-Host 'God of War is not launched and no save/progression file is opened or written.'

    $status = @(& git status --porcelain -- $target)
    if ($LASTEXITCODE -ne 0) { throw 'git status failed.' }
    $status | Set-Content -LiteralPath (Join-Path $logDir 'target-status.txt') -Encoding UTF8

    & git diff -- $target | Set-Content -LiteralPath (Join-Path $logDir 'target-working.diff') -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw 'git diff failed.' }
    & git diff --numstat -- $target | Set-Content -LiteralPath (Join-Path $logDir 'target-numstat.txt') -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw 'git diff --numstat failed.' }

    $workPath = Join-Path $repo $target
    if (-not (Test-Path -LiteralPath $workPath -PathType Leaf)) { throw "Missing worktree file: $target" }
    $workBytes = [System.IO.File]::ReadAllBytes($workPath)
    $workSha = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($workBytes)).ToLowerInvariant()
    $workText = [System.Text.Encoding]::UTF8.GetString($workBytes)

    $headText = (& git show "HEAD:$target") -join "`n"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read HEAD catalogue content.' }
    $headBytes = [System.Text.Encoding]::UTF8.GetBytes($headText)
    $headSha = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($headBytes)).ToLowerInvariant()

    $oldToken = 'parent_has_one_hidden_surplus_raven'
    $newToken = 'parent_contains_one_bonus_untracked_raven'
    $headOld = ([regex]::Matches($headText, [regex]::Escape($oldToken))).Count
    $headNew = ([regex]::Matches($headText, [regex]::Escape($newToken))).Count
    $workOld = ([regex]::Matches($workText, [regex]::Escape($oldToken))).Count
    $workNew = ([regex]::Matches($workText, [regex]::Escape($newToken))).Count

    $headJsonValid = $true
    $workJsonValid = $true
    try { $null = $headText | ConvertFrom-Json -Depth 100 } catch { $headJsonValid = $false }
    try { $null = $workText | ConvertFrom-Json -Depth 100 } catch { $workJsonValid = $false }

    $expectedRename = $headText.Replace($oldToken, $newToken)
    $normalizedWork = $workText.Replace("`r`n", "`n").TrimEnd("`r", "`n")
    $normalizedExpected = $expectedRename.Replace("`r`n", "`n").TrimEnd("`r", "`n")
    $isExactExpectedRename = ($normalizedWork -ceq $normalizedExpected)

    @(
        'result=DIRTY_STATE_INSPECTION_PASSED'
        "timestamp=$(Get-Date -Format o)"
        "branch=$branch"
        "target=$target"
        "status=$($status -join '; ')"
        "worktree_sha256=$workSha"
        "head_text_sha256=$headSha"
        "head_old_metadata_token_count=$headOld"
        "head_new_metadata_token_count=$headNew"
        "worktree_old_metadata_token_count=$workOld"
        "worktree_new_metadata_token_count=$workNew"
        "head_json_valid=$($headJsonValid.ToString().ToLowerInvariant())"
        "worktree_json_valid=$($workJsonValid.ToString().ToLowerInvariant())"
        "worktree_equals_head_plus_expected_metadata_rename=$($isExactExpectedRename.ToString().ToLowerInvariant())"
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
        'inspection_only=true'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8

    Write-Host "Catalogue status: $($status -join '; ')"
    Write-Host "Exact expected metadata rename only: $isExactExpectedRename"
    Write-Host 'DIRTY_STATE_INSPECTION_PASSED'
}
catch {
    $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8
    @(
        'result=DIRTY_STATE_INSPECTION_FAILED'
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
        'inspection_only=true'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8
    Write-Host "DIRTY_STATE_INSPECTION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}

# Publish only the inspection log. Never stage or mutate the dirty catalogue file.
& git add -- $relativeLogDir
if ($LASTEXITCODE -ne 0) { throw 'git add of inspection log failed.' }
& git commit -m "Archive all-Ravens dirty-state inspection $stamp" -- $relativeLogDir
if ($LASTEXITCODE -ne 0) { throw 'git commit of inspection log failed.' }
& git push origin "HEAD:$expectedBranch"
if ($LASTEXITCODE -ne 0) { throw 'git push of inspection log failed.' }

Write-Host 'DIRTY_STATE_INSPECTION_LOG_PUSHED'
