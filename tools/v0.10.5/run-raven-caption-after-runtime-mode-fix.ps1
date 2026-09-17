param(
    [string]$GameRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedRepo = [IO.Path]::GetFullPath('C:\Users\david\Documents\GitHub\completionist-map-gow2018-research-live')
$branch = 'codex/all-collectibles-production-research'
$patcher = Join-Path $PSScriptRoot 'apply-all-ravens-runtime-arg-forwarding.py'
$runtime = Join-Path $PSScriptRoot 'all-ravens-runtime-test.ps1'
$next = Join-Path $PSScriptRoot 'run-raven-reticle-caption-deploy-final-resume.ps1'
$runtimeRelative = 'tools/v0.10.5/all-ravens-runtime-test.ps1'

if ([IO.Path]::GetFullPath($repo) -ne $expectedRepo) {
    throw "Refusing non-isolated checkout: $repo"
}
$currentBranch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $currentBranch -ne $branch) {
    throw "Expected branch '$branch', got '$currentBranch'."
}
if (Get-Process -Name 'GoW','GodOfWar' -ErrorAction SilentlyContinue) {
    throw 'God of War is still running. Close the game first.'
}

# Previous self-logging failures can leave only their own tracked log modified
# after the staged snapshot was committed. Restore only that known residue.
$dirtyBefore = @()
$dirtyBefore += @(& git -C $repo diff --name-only -- | ForEach-Object { $_.Replace('\','/') })
$dirtyBefore += @(& git -C $repo diff --cached --name-only -- | ForEach-Object { $_.Replace('\','/') })
$dirtyBefore = @($dirtyBefore | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique)
foreach ($path in $dirtyBefore) {
    if ($path -notmatch '^archive/field-logs/local-handoffs/raven-reticle-caption-(?:deploy|clean-resume)-\d{8}-\d{6}\.txt$') {
        throw "Unexpected tracked local change before forwarding fix: $path"
    }
}
if ($dirtyBefore.Count -gt 0) {
    & git -C $repo restore --staged --worktree -- $dirtyBefore
    if ($LASTEXITCODE -ne 0) { throw 'Failed to restore known Raven caption log residue.' }
}

& python $patcher | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Runtime argument-forwarding patch failed.' }

$dirtyAfter = @()
$dirtyAfter += @(& git -C $repo diff --name-only -- | ForEach-Object { $_.Replace('\','/') })
$dirtyAfter += @(& git -C $repo diff --cached --name-only -- | ForEach-Object { $_.Replace('\','/') })
$dirtyAfter = @($dirtyAfter | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique)
foreach ($path in $dirtyAfter) {
    if ($path -ne $runtimeRelative) {
        throw "Unexpected tracked change after forwarding patch: $path"
    }
}

& git -C $repo diff --check -- $runtimeRelative | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'git diff --check failed for runtime forwarding fix.' }

if ($runtimeRelative -in $dirtyAfter) {
    & git -C $repo add -- $runtimeRelative
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for runtime forwarding fix.' }
    & git -C $repo commit -m 'fix: preserve all-Ravens transaction action mode' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed for runtime forwarding fix.' }
    & git -C $repo push origin $branch *> $null
    if ($LASTEXITCODE -ne 0) { throw 'git push failed for runtime forwarding fix.' }
}

# Non-destructive regression: Rollback against an impossible root must reach the
# non-Status path and reject that root. If Mode were reset to Status, this would
# incorrectly exit 0 and print ALL_RAVENS_RUNTIME_TEST_STATUS.
$fakeRoot = 'Z:\__completionist_map_nonexistent_runtime_forwarding_test__'
$probeOutput = @(& pwsh -NoProfile -ExecutionPolicy Bypass -File $runtime -Mode Rollback -GameRoot $fakeRoot 2>&1 | ForEach-Object { [string]$_ })
$probeExit = $LASTEXITCODE
$probeText = $probeOutput -join "`n"
if ($probeExit -eq 0) {
    throw 'Runtime forwarding regression failed: Rollback was silently treated as Status.'
}
if ($probeText -notmatch 'God of War root not found') {
    throw "Runtime forwarding regression failed unexpectedly: $probeText"
}
if ($probeText -match 'ALL_RAVENS_RUNTIME_TEST_STATUS') {
    throw 'Runtime forwarding regression emitted Status output.'
}

$args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$next)
if (-not [string]::IsNullOrWhiteSpace($GameRoot)) {
    $args += @('-GameRoot',$GameRoot)
}
& pwsh @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
