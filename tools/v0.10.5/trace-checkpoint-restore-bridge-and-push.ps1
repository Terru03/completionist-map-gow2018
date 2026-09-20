[CmdletBinding()]
param([string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar')

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside repository.'}
Set-Location $RepoRoot
$branch=(& git branch --show-current).Trim()
if($branch-ne $ExpectedBranch){throw "Wrong branch '$branch'; expected '$ExpectedBranch'."}
$staged=@(& git diff --cached --name-only)
if($staged.Count-gt 0){throw "Refusing staged changes: $($staged -join ', ')"}
if(@(Get-Process -ErrorAction SilentlyContinue|Where-Object{$_.ProcessName -in @('GoW','GodOfWar')}).Count-gt 0){throw 'Close God of War before this static trace.'}

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
if(-not(Test-Path -LiteralPath $CapstonePath -PathType Container)){throw "Capstone package path missing: $CapstonePath"}
$Probe=Join-Path $RepoRoot 'tools\v0.10.5\trace-checkpoint-restore-bridge.py'
$Exe=Join-Path $GameRoot 'GoW.exe'
foreach($p in @($Probe,$Exe)){if(-not(Test-Path -LiteralPath $p -PathType Leaf)){throw "Missing required file: $p"}}
$Python=Get-Command python -ErrorAction SilentlyContinue
if(-not $Python){throw 'python.exe not found in PATH.'}

$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$relative="archive/field-logs/source-scans/checkpoint-restore-bridge-$stamp"
$outDir=Join-Path $RepoRoot ($relative -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $outDir|Out-Null
$json=Join-Path $outDir 'report.json'
$text=Join-Path $outDir 'report.txt'
$log=Join-Path $outDir 'console-log.txt'
$published=$false;$transcript=$false

function Stop-LocalTranscript{if($script:transcript){Stop-Transcript|Out-Null;$script:transcript=$false}}
function Publish([string]$Result){
  if($script:published){return}
  Stop-LocalTranscript
  @(
    "result=$Result"
    "timestamp=$(Get-Date -Format o)"
    "branch=$ExpectedBranch"
    "research_index=$Db"
    'scan_only=true'
    'game_launched=false'
    'process_opened=false'
    'active_save_opened=false'
    'game_files_written=false'
    'save_written=false'
    'progression_written=false'
  )|Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8
  & git add -f -- $relative
  if($LASTEXITCODE-ne 0){throw 'git add failed.'}
  & git diff --cached --quiet -- $relative
  if($LASTEXITCODE-eq 1){
    & git commit -m "research(v0.10.5): trace checkpoint restore bridge $stamp" -- $relative|Out-Host
    if($LASTEXITCODE-ne 0){throw 'git commit failed.'}
    & git push origin $ExpectedBranch|Out-Host
    if($LASTEXITCODE-ne 0){throw 'git push failed.'}
  }elseif($LASTEXITCODE-ne 0){throw 'git diff failed.'}
  $script:published=$true
}

try{
  Start-Transcript -LiteralPath $log -Force|Out-Null;$transcript=$true
  Write-Host 'CHECKPOINT RESTORE BRIDGE TRACE - STATIC / READ ONLY' -ForegroundColor Cyan
  Write-Host "Using reusable index: $Db"
  $argsList=@($Probe,'--game-root',$GameRoot,'--db',$Db,'--capstone-path',$CapstonePath,'--output-json',$json,'--output-text',$text)
  & $Python.Source @argsList 2>&1|ForEach-Object{"$_";Write-Host "$_"}
  $code=$LASTEXITCODE
  if($code-ne 0){
    "exit_code=$code"|Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8
    Publish 'CHECKPOINT_RESTORE_BRIDGE_FAILED'
    throw 'Checkpoint restore bridge trace failed.'
  }
  Publish 'CHECKPOINT_RESTORE_BRIDGE_PASSED'
  $head=(& git rev-parse HEAD).Trim()
  Write-Host "CHECKPOINT_RESTORE_BRIDGE_PUSHED $head" -ForegroundColor Green
  Write-Host "Evidence: $relative"
}catch{
  try{$_.Exception.ToString()|Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8}catch{}
  if(-not $published){try{Publish 'CHECKPOINT_RESTORE_BRIDGE_FAILED'}catch{Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red}}
  Write-Host "CHECKPOINT_RESTORE_BRIDGE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}finally{Stop-LocalTranscript}
