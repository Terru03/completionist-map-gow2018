[CmdletBinding()]
param([string]$GameRoot='G:\\SteamLibrary\\steamapps\\common\\GodOfWar')

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
if(@(Get-Process -ErrorAction SilentlyContinue|Where-Object{$_.ProcessName -in @('GoW','GodOfWar')}).Count-gt 0){
  throw 'Close God of War before this static executable trace.'
}

$IndexName='gow-caebcb027980.sqlite'
$Parent=Split-Path -Parent $RepoRoot
$IndexRoots=@(
  (Join-Path $RepoRoot '.research-index'),
  (Join-Path $Parent 'completionist-map-gow2018-all-collectibles-production-research\.research-index')
)
$IndexRoot=$IndexRoots|Where-Object{Test-Path -LiteralPath (Join-Path $_ $IndexName) -PathType Leaf}|Select-Object -First 1
if([string]::IsNullOrWhiteSpace($IndexRoot)){throw "Research index not found: $($IndexRoots -join ' ; ')"}
$Db=Join-Path $IndexRoot $IndexName
$CapstonePath=Join-Path $IndexRoot 'python-packages'
$Probe=Join-Path $RepoRoot 'tools\v0.10.5\trace-raven-staged-restore-records.py'
$Exe=Join-Path $GameRoot 'GoW.exe'
foreach($p in @($Probe,$Exe)){if(-not(Test-Path -LiteralPath $p -PathType Leaf)){throw "Missing required file: $p"}}
if(-not(Test-Path -LiteralPath $CapstonePath -PathType Container)){throw "Capstone package path missing: $CapstonePath"}
$Python=Get-Command python -ErrorAction SilentlyContinue
if(-not $Python){throw 'python.exe not found in PATH.'}

$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relative="archive/field-logs/source-scans/raven-staged-restore-records-$stamp"
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

Write-Host 'RAVEN STAGED RESTORE RECORD TRACE - STATIC / READ ONLY'
Write-Host 'Proves LuaClient +0x80 restore ownership and narrows staged WAD checkpoint storage.'
Write-Host 'No game launch, process access, save access, progression writes, or game-file writes.'
Write-Host ''

$lines=& $Python.Source $Probe --exe $Exe --db $Db --capstone-path $CapstonePath --output-json $json --output-text $text 2>&1 |
  ForEach-Object {"$_";Write-Host "$_"}
$code=$LASTEXITCODE
$lines|Set-Content -LiteralPath $log -Encoding UTF8
if($code-ne 0){
  Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Value "exit_code=$code" -Encoding UTF8
}

Invoke-Git @('add','-f','--',$relative)
$message=if($code-eq 0){
  "research(v0.10.5): trace Raven staged restore records $stamp"
}else{
  "research(v0.10.5): archive failed Raven staged restore trace $stamp"
}
Invoke-Git @('commit','-m',$message,'--',$relative)
Invoke-Git @('push','origin',$ExpectedBranch)
$head=(& git -C $RepoRoot rev-parse HEAD).Trim()

if($code-ne 0){throw "Raven staged restore trace failed; evidence pushed in $head"}
Write-Host ''
Write-Host "RAVEN_STAGED_RESTORE_RECORDS_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relative"
