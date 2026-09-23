# No param block: this recorder starts before branch, Git, or inner-script binding.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branchWanted = 'codex/collectible-legendary-chests'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$external = Join-Path $env:LOCALAPPDATA "CompletionistMap/legendary-live-test/$stamp"
$transcript = Join-Path $external 'terminal.txt'
$result = 'FAILED'
$failure = $null
$branch = $null
$headBefore = $null
$headAfter = $null
$transcriptStarted = $false
$archiveRelative = "archive/field-logs/runtime-captures/legendary-live-test-marker-prepare-$stamp"

try {
    New-Item -ItemType Directory -Force -Path $external | Out-Null
    Start-Transcript -LiteralPath $transcript -Force | Out-Null
    $transcriptStarted = $true
    Write-Host "LEGENDARY_OUTER_RECORD_STARTED external=$external"
    Set-Location -LiteralPath $repoRoot
    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne $branchWanted) { throw "Wrong branch before pull: $branch" }
    $dirty = @(& git status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0 -or $dirty.Count -ne 0) { throw "Dirty tree before pull: $($dirty -join ', ')" }
    $headBefore = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not read Git HEAD before pull.' }
    Write-Host "LEGENDARY_PREPULL_BRANCH=$branch HEAD=$headBefore"
    & git pull --ff-only origin $branchWanted
    if ($LASTEXITCODE -ne 0) { throw 'git pull --ff-only failed.' }
    $branch = (& git branch --show-current).Trim()
    $headAfter = (& git rev-parse HEAD).Trim()
    $dirty = @(& git status --porcelain --untracked-files=normal)
    if ($branch -ne $branchWanted -or $dirty.Count -ne 0) { throw 'Branch or tree changed after pull.' }
    Write-Host "LEGENDARY_POSTPULL_BRANCH=$branch HEAD=$headAfter"
    & (Join-Path $repoRoot 'tools/v0.10.5/install-legendary-live-test-marker.ps1') -EvidenceRoot $external
    if (-not $?) { throw 'Inner installer returned failure.' }
    $result = 'PREPARED_NO_GAME_LAUNCH'
    Write-Host "LEGENDARY_OUTER_PREPARED external=$external"
}
catch {
    $failure = $_.Exception.Message
    Write-Host "LEGENDARY_OUTER_FAILED reason=$failure"
}
finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
    $record = [ordered]@{
        schema = 1
        result = $result
        failure = $failure
        branch = $branch
        head_before_pull = $headBefore
        head_after_pull = $headAfter
        external_evidence = $external
        terminal = $transcript
        created_utc = (Get-Date).ToUniversalTime().ToString('o')
        game_launched = $false
    }
    try {
        New-Item -ItemType Directory -Force -Path $external | Out-Null
        $record | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $external 'outer-result.json') -Encoding UTF8
        if ($branch -eq $branchWanted) {
            $nowBranch = (& git -C $repoRoot branch --show-current).Trim()
            if ($nowBranch -ne $branchWanted) { throw "Cannot archive on changed branch: $nowBranch" }
            $archive = Join-Path $repoRoot $archiveRelative
            New-Item -ItemType Directory -Force -Path $archive | Out-Null
            foreach ($item in @(Get-ChildItem -LiteralPath $external)) {
                Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $archive $item.Name) -Force -Recurse
            }
            & git -C $repoRoot add -f -- $archiveRelative
            if ($LASTEXITCODE -ne 0) { throw 'Could not stage terminal archive.' }
            & git -C $repoRoot commit -m "Archive Legendary live-test preparation $result $stamp" -- $archiveRelative
            if ($LASTEXITCODE -ne 0) { throw 'Could not commit terminal archive.' }
            & git -C $repoRoot push origin $branchWanted
            if ($LASTEXITCODE -ne 0) { throw 'Could not push terminal archive.' }
            Write-Host "LEGENDARY_OUTER_ARCHIVED commit=$((& git -C $repoRoot rev-parse HEAD).Trim())"
        } else {
            Write-Host "LEGENDARY_OUTER_EXTERNAL_ONLY wrong_branch=$branch evidence=$external"
        }
    }
    catch {
        $archiveFailure = $_.Exception.Message
        "archive_failure=$archiveFailure" | Set-Content -LiteralPath (Join-Path $external 'archive-failure.txt') -Encoding UTF8
        Write-Host "LEGENDARY_OUTER_ARCHIVE_FAILED reason=$archiveFailure external=$external"
        $result = 'FAILED'
    }
}
Write-Host "LEGENDARY_OUTER_RESULT=$result evidence=$external"
if ($result -ne 'PREPARED_NO_GAME_LAUNCH') { exit 1 }
