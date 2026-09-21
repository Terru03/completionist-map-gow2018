[CmdletBinding()]
param(
    [string]$EvidenceDir=''
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside the Completionist Map repository.'}
Set-Location $RepoRoot

$Probe=Join-Path $RepoRoot 'tools\v0.10.5\compact-lua-vfs-registry-report.py'

function Invoke-Git {
    param([string[]]$GitArgs)
    & git -C $RepoRoot @GitArgs | Out-Host
    if($LASTEXITCODE -ne 0){throw "git $($GitArgs -join ' ') failed"}
}

$branch=(& git -C $RepoRoot branch --show-current).Trim()
if($branch-ne $ExpectedBranch){throw "Wrong branch '$branch'; expected '$ExpectedBranch'."}
$staged=@(& git -C $RepoRoot diff --cached --name-only)
if($staged.Count -gt 0){throw "Refusing pre-existing staged changes: $($staged -join ', ')"}

if([string]::IsNullOrWhiteSpace($EvidenceDir)){
    $scanRoot=Join-Path $RepoRoot 'archive\field-logs\source-scans'
    $candidate=Get-ChildItem -LiteralPath $scanRoot -Directory |
        Where-Object { $_.Name -like 'lua-vfs-registry-*' -and (Test-Path -LiteralPath (Join-Path $_.FullName 'report.json')) } |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if(-not $candidate){throw 'No completed lua-vfs-registry evidence directory was found.'}
    $EvidenceDir=$candidate.FullName
} elseif(-not [IO.Path]::IsPathRooted($EvidenceDir)){
    $EvidenceDir=Join-Path $RepoRoot $EvidenceDir
}

$InputJson=Join-Path $EvidenceDir 'report.json'
$SummaryJson=Join-Path $EvidenceDir 'summary.json'
$SummaryText=Join-Path $EvidenceDir 'summary.txt'
$SummaryLog=Join-Path $EvidenceDir 'compact-console-log.txt'

foreach($p in @($Probe,$InputJson)){
    if(-not(Test-Path -LiteralPath $p -PathType Leaf)){throw "Required file missing: $p"}
}

$python=Get-Command python -ErrorAction SilentlyContinue
if(-not $python){throw 'python.exe was not found in PATH.'}

Write-Host 'LUA VFS REGISTRY REPORT COMPACTION - EXISTING EVIDENCE ONLY'
$lines=& $python.Source $Probe --input $InputJson --output-json $SummaryJson --output-text $SummaryText 2>&1 |
    ForEach-Object{"$_"; Write-Host "$_"}
$code=$LASTEXITCODE
$lines | Set-Content -LiteralPath $SummaryLog -Encoding UTF8

if($code-ne 0){throw "VFS registry evidence compaction failed with exit code $code"}

$relativeDir=[IO.Path]::GetRelativePath($RepoRoot,$EvidenceDir).Replace('\','/')
Invoke-Git @('add','-f','--',"$relativeDir/summary.json","$relativeDir/summary.txt","$relativeDir/compact-console-log.txt")
Invoke-Git @('commit','-m',"research(v0.10.5): compact Lua VFS registry evidence", '--',
    "$relativeDir/summary.json","$relativeDir/summary.txt","$relativeDir/compact-console-log.txt")
Invoke-Git @('push','origin',$ExpectedBranch)

$head=(& git -C $RepoRoot rev-parse HEAD).Trim()
Write-Host ''
Write-Host "LUA_VFS_REGISTRY_COMPACT_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
