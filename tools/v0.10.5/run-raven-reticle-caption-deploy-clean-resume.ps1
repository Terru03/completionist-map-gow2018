param(
    [string]$GameRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedRepo = [IO.Path]::GetFullPath('C:\Users\david\Documents\GitHub\completionist-map-gow2018-research-live')
$expectedBranch = 'codex/all-collectibles-production-research'
$deploy = Join-Path $PSScriptRoot 'run-raven-reticle-caption-deploy-with-log.ps1'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDir = Join-Path $repo 'archive\field-logs\local-handoffs'
$guardLog = Join-Path $logDir "raven-reticle-caption-clean-resume-$stamp.txt"
$guardLogRelative = [IO.Path]::GetRelativePath($repo, $guardLog).Replace('\','/')
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-GuardLog([string]$Text) {
    Add-Content -LiteralPath $guardLog -Value $Text -Encoding UTF8
}

function Push-GuardFailure([string]$Message, [string[]]$DirtyPaths) {
    Write-GuardLog 'RAVEN_RETICLE_CAPTION_CLEAN_RESUME'
    Write-GuardLog "RESULT=FAILED"
    Write-GuardLog "ERROR=$Message"
    foreach ($path in $DirtyPaths) { Write-GuardLog "DIRTY_PATH=$path" }
    Write-GuardLog 'GAME_FILES_TOUCHED=false'
    & git -C $repo add -- $guardLogRelative | Out-Null
    & git -C $repo commit -m 'logs: capture Raven caption clean-resume refusal' | Out-Null
    if ($LASTEXITCODE -eq 0) { & git -C $repo push origin $expectedBranch | Out-Null }
    Write-Host 'DONE'
    exit 0
}

if ([IO.Path]::GetFullPath($repo) -ne $expectedRepo) {
    Push-GuardFailure "Refusing non-isolated checkout: $repo" @()
}
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $expectedBranch) {
    Push-GuardFailure "Expected branch '$expectedBranch', got '$branch'." @()
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

$unexpected = @($dirty | Where-Object { $_ -notin $allowed })
if ($unexpected.Count -gt 0) {
    Push-GuardFailure 'Unexpected tracked local changes; refusing cleanup.' $dirty
}

if ($dirty.Count -gt 0) {
    foreach ($path in $dirty) { Write-GuardLog "RESTORING_KNOWN_RESIDUE=$path" }
    & git -C $repo restore --staged --worktree -- $dirty
    if ($LASTEXITCODE -ne 0) {
        Push-GuardFailure 'Failed to restore known deployment residue.' $dirty
    }
}

& git -C $repo diff --quiet --ignore-submodules --
if ($LASTEXITCODE -ne 0) { Push-GuardFailure 'Tracked working-tree changes remain after guarded cleanup.' $dirty }
& git -C $repo diff --cached --quiet --ignore-submodules --
if ($LASTEXITCODE -ne 0) { Push-GuardFailure 'Staged changes remain after guarded cleanup.' $dirty }

Remove-Item -LiteralPath $guardLog -Force -ErrorAction SilentlyContinue

$args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$deploy)
if (-not [string]::IsNullOrWhiteSpace($GameRoot)) {
    $args += @('-GameRoot',$GameRoot)
}
& pwsh @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
