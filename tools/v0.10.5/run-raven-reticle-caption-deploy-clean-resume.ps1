param(
    [string]$GameRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedRepo = [IO.Path]::GetFullPath('C:\Users\david\Documents\GitHub\completionist-map-gow2018-research-live')
$expectedBranch = 'codex/all-collectibles-production-research'
$deploy = Join-Path $PSScriptRoot 'run-raven-reticle-caption-deploy-with-log.ps1'

if ([IO.Path]::GetFullPath($repo) -ne $expectedRepo) {
    throw "Refusing non-isolated checkout: $repo"
}
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $expectedBranch) {
    throw "Expected branch '$expectedBranch', got '$branch'."
}

$allowed = @(
    'tools/v0.10.5/all-ravens-map-runtime.lua',
    'tools/v0.10.5/test_all_ravens_lua.py',
    'archive/all-ravens/all-ravens-release-candidate-offline.json',
    'archive/all-ravens/all-ravens-transaction-self-test.json'
)

$dirty = @()
$dirty += @(& git -C $repo diff --name-only -- | ForEach-Object { $_.Replace('\','/') })
$dirty += @(& git -C $repo diff --cached --name-only -- | ForEach-Object { $_.Replace('\','/') })
$dirty = @($dirty | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique)

foreach ($path in $dirty) {
    if ($path -notin $allowed) {
        throw "Unexpected tracked local change; refusing cleanup: $path"
    }
}

if ($dirty.Count -gt 0) {
    & git -C $repo restore --staged --worktree -- $dirty
    if ($LASTEXITCODE -ne 0) { throw 'Failed to restore known deployment residue.' }
}

& git -C $repo diff --quiet --ignore-submodules --
if ($LASTEXITCODE -ne 0) { throw 'Tracked working-tree changes remain after guarded cleanup.' }
& git -C $repo diff --cached --quiet --ignore-submodules --
if ($LASTEXITCODE -ne 0) { throw 'Staged changes remain after guarded cleanup.' }

$args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$deploy)
if (-not [string]::IsNullOrWhiteSpace($GameRoot)) {
    $args += @('-GameRoot',$GameRoot)
}
& pwsh @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
