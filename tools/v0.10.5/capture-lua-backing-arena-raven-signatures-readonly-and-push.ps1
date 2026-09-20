[CmdletBinding()]
param()

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside the Completionist Map repository.'}
Set-Location $RepoRoot

$Capture=Join-Path $RepoRoot 'tools\v0.10.5\capture-lua-backing-arena-raven-signatures-readonly.py'
$Identities=Join-Path $RepoRoot 'catalogue\odins-ravens-save-identities.json'
$sourceRoot=Join-Path $RepoRoot 'archive\field-logs\runtime-captures'
$source=Get-ChildItem -LiteralPath $sourceRoot -Directory |
  Where-Object {$_.Name -like 'lua-context-backing-cache-readonly-*'} |
  Sort-Object Name -Descending |
  Select-Object -First 1
if(-not $source){throw 'No LuaContext backing-cache capture found.'}
$SourceReport=Join-Path $source.FullName 'report.json'

$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir="archive/field-logs/runtime-captures/lua-backing-arena-raven-signatures-readonly-$stamp"
$outDir=Join-Path $RepoRoot ($relativeDir -replace '/',[IO.Path]::DirectorySeparatorChar)
$outJson=Join-Path $outDir 'report.json'
$outText=Join-Path $outDir 'report.txt'
$console=Join-Path $outDir 'console-log.txt'

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
foreach($path in @($Capture,$Identities,$SourceReport)){
  if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "Missing required file: $path"}
}
$running=@(Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -in @('GoW','GodOfWar')})
if($running.Count-ne 1){throw 'Keep the same God of War session running from the previous cache capture.'}
$python=Get-Command python -ErrorAction SilentlyContinue
if(-not $python){throw 'python.exe was not found in PATH.'}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Write-Host 'LUA BACKING ARENA RAVEN SIGNATURE SCAN - READ ONLY'
Write-Host "Source cache capture: $($source.Name)"
Write-Host 'Keep the same loaded God of War session running. No gameplay action is required.'
Write-Host 'Scans only the six proven non-empty backing caches for Raven/checkpoint signatures.'
Write-Host 'Arena-capacity hits are diagnostic physical-presence evidence only, not yet authoritative state.'
Write-Host ''

$lines=& $python.Source $Capture --source-report $SourceReport --identities $Identities --output-json $outJson --output-text $outText 2>&1 |
  ForEach-Object {"$_";Write-Host "$_"}
$code=$LASTEXITCODE
$lines|Set-Content -LiteralPath $console -Encoding UTF8
if($code-ne 0){Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Value "exit_code=$code" -Encoding UTF8}

Invoke-Git @('add','-f','--',$relativeDir)
$message=if($code-eq 0){
  "research(v0.10.5): scan Lua backing arenas for Raven signatures read-only $stamp"
}else{
  "research(v0.10.5): archive failed Raven backing-arena signature scan $stamp"
}
Invoke-Git @('commit','-m',$message,'--',$relativeDir)
Invoke-Git @('push','origin',$ExpectedBranch)
$head=(& git -C $RepoRoot rev-parse HEAD).Trim()

if($code-ne 0){throw "Read-only Raven backing-arena signature scan failed; evidence pushed in $head"}

Write-Host ''
Write-Host "LUA_BACKING_ARENA_RAVEN_SIGNATURES_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
