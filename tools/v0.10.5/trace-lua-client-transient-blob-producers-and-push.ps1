[CmdletBinding()]
param([string]$Exe='G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe')

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside the Completionist Map repository.'}
Set-Location $RepoRoot

$Probe=Join-Path $RepoRoot 'tools\v0.10.5\trace-lua-client-transient-blob-producers.py'
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir="archive/field-logs/source-scans/lua-client-transient-blob-producers-$stamp"
$outDir=Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$json=Join-Path $outDir 'report.json'
$text=Join-Path $outDir 'report.txt'
$log=Join-Path $outDir 'console-log.txt'

function Invoke-Git {
  param([Parameter(Mandatory=$true)][string[]]$GitArgs)
  & git -C $RepoRoot @GitArgs | Out-Host
  if($LASTEXITCODE-ne 0){throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"}
}

$branch=(& git -C $RepoRoot branch --show-current).Trim()
if($branch-ne $ExpectedBranch){throw "Wrong branch '$branch'; expected '$ExpectedBranch'."}
$staged=@(& git -C $RepoRoot diff --cached --name-only)
if($LASTEXITCODE-ne 0){throw 'Unable to inspect staged changes.'}
if($staged.Count-gt 0){throw "Refusing pre-existing staged changes: $($staged -join ', ')"}
if(@(Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -in @('GoW','GodOfWar')}).Count-gt 0){
  throw 'Close God of War before this static executable scan.'
}
foreach($path in @($Probe,$Exe)){
  if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "Required file missing: $path"}
}
$python=Get-Command python -ErrorAction SilentlyContinue
if(-not $python){throw 'python.exe was not found in PATH.'}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Write-Host 'LUA CLIENT TRANSIENT BLOB PRODUCER SCAN - STATIC / READ ONLY'
Write-Host 'Finds whole-executable writers of LuaClient +0x70/+0x78/+0x80 and ranks producer candidates.'
Write-Host 'No save access, game launch, progression writes, or game-file writes.'
Write-Host ''

$lines=& $python.Source $Probe --exe $Exe --output-json $json --output-text $text 2>&1 |
  ForEach-Object {"$_"; Write-Host "$_"}
$code=$LASTEXITCODE
$lines|Set-Content -LiteralPath $log -Encoding UTF8
if($code-ne 0){
  Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Value "exit_code=$code" -Encoding UTF8
}

Invoke-Git @('add','-f','--',$relativeDir)
$message=if($code-eq 0){
  "research(v0.10.5): scan LuaClient transient blob producers $stamp"
}else{
  "research(v0.10.5): archive failed LuaClient transient blob producer scan $stamp"
}
Invoke-Git @('commit','-m',$message,'--',$relativeDir)
Invoke-Git @('push','origin',$ExpectedBranch)
$head=(& git -C $RepoRoot rev-parse HEAD).Trim()

if($code-ne 0){throw "LuaClient transient blob producer scan failed; evidence pushed in $head"}

Write-Host ''
Write-Host "LUA_CLIENT_TRANSIENT_BLOB_PRODUCER_SCAN_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
