param(
    [string]$GameRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedRepo = [IO.Path]::GetFullPath('C:\Users\david\Documents\GitHub\completionist-map-gow2018-research-live')
$expectedBranch = 'codex/all-collectibles-production-research'
$next = Join-Path $PSScriptRoot 'run-raven-reticle-caption-deploy-clean-resume.ps1'

if ([IO.Path]::GetFullPath($repo) -ne $expectedRepo) {
    throw "Refusing non-isolated checkout: $repo"
}
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $expectedBranch) {
    throw "Expected branch '$expectedBranch', got '$branch'."
}

$dirty = @()
$dirty += @(& git -C $repo diff --name-only -- | ForEach-Object { $_.Replace('\\','/') })
$dirty += @(& git -C $repo diff --cached --name-only -- | ForEach-Object { $_.Replace('\\','/') })
$dirty = @($dirty | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique)

$logResidue = @()
foreach ($path in $dirty) {
    if ($path -match '^archive/field-logs/local-handoffs/raven-reticle-caption-(?:deploy|clean-resume)-\d{8}-\d{6}\.txt$') {
        $logResidue += $path
    }
}

if ($logResidue.Count -gt 0) {
    & git -C $repo restore --staged --worktree -- $logResidue
    if ($LASTEXITCODE -ne 0) { throw 'Failed to restore known Raven caption log residue.' }
}

$args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$next)
if (-not [string]::IsNullOrWhiteSpace($GameRoot)) {
    $args += @('-GameRoot',$GameRoot)
}
& pwsh @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
