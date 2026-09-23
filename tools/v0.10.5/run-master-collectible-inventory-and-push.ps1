[CmdletBinding()]
param(
    [string]$ExpectedBranch = 'codex/master-collectible-inventory',
    [string]$SeedBranch = 'codex/collectible-ship-heads'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relative = "archive/field-logs/master-inventory/master-collectible-inventory-$stamp"
$out = Join-Path $repo $relative
$transcript = Join-Path $out 'console-log.txt'
$transcriptStarted = $false
$published = $false
$prechecksPassed = $false
$result = 'FAIL_PRECHECK'

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
        $script:transcriptStarted = $false
    }
}

function Publish-Result([string]$state) {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    @(
        "result=$state"
        "timestamp=$(Get-Date -Format o)"
        "branch=$ExpectedBranch"
        "seed_branch=$SeedBranch"
        "runtime_generation_allowed=false"
        "game_process_access=false"
        "game_files_written=false"
    ) | Set-Content -LiteralPath (Join-Path $out 'result.txt') -Encoding UTF8
    & git add -f -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relative
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "research(v0.10.5): archive master collectible inventory $stamp" -- $relative
        if ($LASTEXITCODE -ne 0) { throw 'inventory evidence commit failed.' }
    } elseif ($LASTEXITCODE -ne 0) { throw 'git diff --cached failed.' }
    & git fetch origin $ExpectedBranch
    if ($LASTEXITCODE -ne 0) { throw 'fetch before evidence push failed.' }
    & git rebase "origin/$ExpectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'rebase before evidence push failed; evidence commit remains local.' }
    & git push origin "HEAD:$ExpectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'evidence push failed; evidence commit remains local.' }
}

try {
    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $ExpectedBranch) { throw "Wrong branch '$branch'; expected '$ExpectedBranch'." }
    if (@(& git status --porcelain).Count -gt 0) { throw 'Working tree must be clean before master inventory run.' }
    $prechecksPassed = $true

    New-Item -ItemType Directory -Force -Path $out | Out-Null
    Start-Transcript -LiteralPath $transcript -Force | Out-Null
    $transcriptStarted = $true

    & git fetch origin $ExpectedBranch $SeedBranch 'codex/all-ravens-release-candidate' 'codex/collectible-legendary-chests' 'codex/collectible-nornir-chests' 'codex/collectible-artefacts' 'codex/collectible-lore-markers'
    if ($LASTEXITCODE -ne 0) { throw 'git fetch of inventory/family branches failed.' }

    & python '.\tools\v0.10.5\export-master-collectible-sources.py' --output-dir $out --seed-branch $SeedBranch
    if ($LASTEXITCODE -ne 0) { throw 'pinned family source export failed.' }
    $env:MASTER_SOURCE_MANIFEST = Join-Path $out 'source-manifest.json'
    & python '.\tools\v0.10.5\test_master_collectible_inventory.py'
    if ($LASTEXITCODE -ne 0) { throw 'master inventory unit tests failed.' }

    & python '.\tools\v0.10.5\build-master-collectible-inventory.py' --source-manifest $env:MASTER_SOURCE_MANIFEST --output-dir $out
    if ($LASTEXITCODE -ne 0) { throw 'master collectible inventory builder failed.' }

    Copy-Item '.\config\collectibles\v0.10.5\master-collectible-policy.json' (Join-Path $out 'master-collectible-policy.json') -Force
    $result = 'PASS_EVIDENCE_ONLY_FAIL_CLOSED'
    Publish-Result $result
    Write-Host "MASTER_COLLECTIBLE_INVENTORY_PUSHED $relative"
}
catch {
    if (-not $prechecksPassed) { throw }
    try {
        New-Item -ItemType Directory -Force -Path $out | Out-Null
        $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $out 'error.txt') -Encoding UTF8
    } catch {}
    try { Publish-Result "FAIL_EVIDENCE_ONLY: $($_.Exception.Message)" } catch {
        Write-Host "MASTER_INVENTORY_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
    throw
}
finally {
    Stop-LocalTranscript
    Remove-Item Env:MASTER_SOURCE_MANIFEST -ErrorAction SilentlyContinue
}
