[CmdletBinding()]
param()

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside the Completionist Map repository.'}
Set-Location $RepoRoot

$Tool=Join-Path $RepoRoot 'tools\v0.10.5\compact-lua-backing-cache-node-layout.py'
$branch=(& git -C $RepoRoot branch --show-current).Trim()
if($branch-ne $ExpectedBranch){throw "Wrong branch '$branch'; expected '$ExpectedBranch'."}
$staged=@(& git -C $RepoRoot diff --cached --name-only)
if($LASTEXITCODE-ne 0){throw 'Unable to inspect staged changes.'}
if($staged.Count-gt 0){throw "Refusing pre-existing staged changes: $($staged -join ', ')"}
if(-not(Test-Path -LiteralPath $Tool -PathType Leaf)){throw "Required tool missing: $Tool"}

$root=Join-Path $RepoRoot 'archive\field-logs\source-scans'
$src=Get-ChildItem -LiteralPath $root -Directory |
  Where-Object {$_.Name -like 'lua-backing-cache-node-layout-*'} |
  Sort-Object Name -Descending |
  Select-Object -First 1
if(-not $src){throw 'No lua-backing-cache-node-layout capture found.'}

$report=Join-Path $src.FullName 'report.json'
if(-not(Test-Path -LiteralPath $report -PathType Leaf)){throw "Missing report.json in $($src.FullName)"}

$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir="archive/field-logs/source-scans/lua-backing-cache-node-compact-$stamp"
$outDir=Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$outJson=Join-Path $outDir 'summary.json'
$outText=Join-Path $outDir 'summary.txt'
$log=Join-Path $outDir 'console-log.txt'

$python=Get-Command python -ErrorAction SilentlyContinue
if(-not $python){throw 'python.exe was not found in PATH.'}

Write-Host 'LUA BACKING CACHE NODE COMPACT EXTRACT - POSTPROCESS ONLY'
Write-Host "Source: $($src.Name)"
Write-Host 'No executable scan, no game launch, no process access, no save access.'
Write-Host ''

$lines=& $python.Source $Tool --report-json $report --output-json $outJson --output-text $outText 2>&1 |
  ForEach-Object {"$_"; Write-Host "$_"}
$code=$LASTEXITCODE
$lines|Set-Content -LiteralPath $log -Encoding UTF8
if($code-ne 0){
  Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Value "exit_code=$code" -Encoding UTF8
}

function Invoke-Git {
  param([Parameter(Mandatory=$true)][string[]]$GitArgs)
  & git -C $RepoRoot @GitArgs | Out-Host
  if($LASTEXITCODE-ne 0){throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"}
}

Invoke-Git @('add','-f','--',$relativeDir)
$message=if($code-eq 0){
  "research(v0.10.5): compact durable Lua backing cache node $stamp"
}else{
  "research(v0.10.5): archive failed compact backing cache node $stamp"
}
Invoke-Git @('commit','-m',$message,'--',$relativeDir)
Invoke-Git @('push','origin',$ExpectedBranch)
$head=(& git -C $RepoRoot rev-parse HEAD).Trim()

if($code-ne 0){throw "Compact backing-cache extraction failed; evidence pushed in $head"}

Write-Host ''
Write-Host "LUA_BACKING_CACHE_NODE_COMPACT_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
