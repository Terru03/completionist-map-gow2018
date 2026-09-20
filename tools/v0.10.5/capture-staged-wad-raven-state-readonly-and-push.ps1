[CmdletBinding()]
param()

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside the Completionist Map repository.'}
Set-Location $RepoRoot

$branch=(& git branch --show-current).Trim()
if($branch-ne $ExpectedBranch){throw "Wrong branch '$branch'; expected '$ExpectedBranch'."}
$staged=@(& git diff --cached --name-only)
if($staged.Count-gt 0){throw "Refusing pre-existing staged changes: $($staged -join ', ')"}

$Probe=Join-Path $RepoRoot 'tools\v0.10.5\capture-staged-wad-raven-state-readonly.py'
$Identities=Join-Path $RepoRoot 'catalogue\odins-ravens-save-identities.json'
foreach($p in @($Probe,$Identities)){if(-not(Test-Path -LiteralPath $p -PathType Leaf)){throw "Missing required file: $p"}}
$Python=Get-Command python -ErrorAction SilentlyContinue
if(-not $Python){throw 'python.exe not found in PATH.'}

$gow=@(Get-Process -ErrorAction SilentlyContinue|Where-Object{$_.ProcessName -in @('GoW','GodOfWar')})
if($gow.Count-ne 1){throw 'Start God of War and load the save you want to test, then run this command again.'}

$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relative="archive/field-logs/runtime-captures/staged-wad-raven-state-readonly-$stamp"
$outDir=Join-Path $RepoRoot ($relative -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $outDir|Out-Null
$json=Join-Path $outDir 'report.json'
$text=Join-Path $outDir 'report.txt'
$log=Join-Path $outDir 'console-log.txt'

function Invoke-Git {
  param([Parameter(Mandatory=$true)][string[]]$GitArgs)
  & git -C $RepoRoot @GitArgs | Out-Host
  if($LASTEXITCODE-ne 0){throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"}
}

Write-Host 'STAGED WAD RAVEN STATE - READ ONLY'
Write-Host 'Keep God of War running on the loaded save. No gameplay action is required.'
Write-Host 'Reads only the proven staged WAD record table and its referenced payload extents.'
Write-Host 'No debugger, no process writes, no save reads/writes, no progression writes.'
Write-Host ''

$lines=& $Python.Source $Probe --identities $Identities --output-json $json --output-text $text 2>&1 |
  ForEach-Object {"$_";Write-Host "$_"}
$code=$LASTEXITCODE
$lines|Set-Content -LiteralPath $log -Encoding UTF8
if($code-ne 0){
  Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Value "exit_code=$code" -Encoding UTF8
}

Invoke-Git @('add','-f','--',$relative)
$message=if($code-eq 0){
  "research(v0.10.5): capture staged WAD Raven state $stamp"
}else{
  "research(v0.10.5): archive failed staged WAD Raven state $stamp"
}
Invoke-Git @('commit','-m',$message,'--',$relative)
Invoke-Git @('push','origin',$ExpectedBranch)
$head=(& git -C $RepoRoot rev-parse HEAD).Trim()

if($code-ne 0){throw "Staged WAD Raven state capture failed; evidence pushed in $head"}
Write-Host ''
Write-Host "STAGED_WAD_RAVEN_STATE_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relative"
