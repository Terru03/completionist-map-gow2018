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
$Probe=Join-Path $RepoRoot 'tools\v0.10.5\capture-staged-wad-subobject-keys-readonly.py'
if(-not(Test-Path -LiteralPath $Probe -PathType Leaf)){throw "Missing probe: $Probe"}
$Python=Get-Command python -ErrorAction SilentlyContinue
if(-not $Python){throw 'python.exe not found in PATH.'}
$gow=@(Get-Process -ErrorAction SilentlyContinue|Where-Object{$_.ProcessName -in @('GoW','GodOfWar')})
if($gow.Count-ne 1){throw 'Keep exactly one God of War process running on the loaded save.'}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relative="archive/field-logs/runtime-captures/staged-wad-subobject-keys-readonly-$stamp"
$outDir=Join-Path $RepoRoot ($relative -replace '/',[IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $outDir|Out-Null
$json=Join-Path $outDir 'report.json';$text=Join-Path $outDir 'report.txt';$log=Join-Path $outDir 'console-log.txt'
function Invoke-Git {param([Parameter(Mandatory=$true)][string[]]$GitArgs);& git -C $RepoRoot @GitArgs|Out-Host;if($LASTEXITCODE-ne 0){throw "git $($GitArgs -join ' ') failed"}}
Write-Host 'STAGED WAD SUBOBJECT KEYS - READ ONLY'
Write-Host 'Keep God of War running on the loaded save. No gameplay action is required.'
Write-Host 'Reads only the proven staged WAD table/payload pool and extracts __subobjs custom-record keys.'
Write-Host 'No debugger, no process writes, no save reads/writes, no progression writes.'
$lines=& $Python.Source $Probe --output-json $json --output-text $text 2>&1|ForEach-Object{"$_";Write-Host "$_"}
$code=$LASTEXITCODE;$lines|Set-Content -LiteralPath $log -Encoding UTF8
if($code-ne 0){Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Value "exit_code=$code" -Encoding UTF8}
Invoke-Git @('add','-f','--',$relative)
$msg=if($code-eq 0){"research(v0.10.5): capture staged WAD SubObject keys $stamp"}else{"research(v0.10.5): archive failed staged WAD SubObject keys $stamp"}
Invoke-Git @('commit','-m',$msg,'--',$relative);Invoke-Git @('push','origin',$ExpectedBranch)
$head=(& git -C $RepoRoot rev-parse HEAD).Trim()
if($code-ne 0){throw "Staged WAD SubObject key capture failed; evidence pushed in $head"}
Write-Host "STAGED_WAD_SUBOBJECT_KEYS_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relative"
