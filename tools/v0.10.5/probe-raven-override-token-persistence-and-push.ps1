[CmdletBinding()]
param(
    [string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$SaveRoot="$HOME\Saved Games\God of War"
)

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Probe=Join-Path $PSScriptRoot 'probe-raven-override-token-persistence.py'
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir="archive/field-logs/save-forensics/raven-override-token-persistence-$stamp"
$outDir=Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$json=Join-Path $outDir 'report.json'
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
    throw 'Close God of War before this read-only active-save probe.'
}
if(-not(Test-Path -LiteralPath $Probe -PathType Leaf)){throw "Missing probe: $Probe"}
if(-not(Test-Path -LiteralPath $GameRoot -PathType Container)){throw "Game root not found: $GameRoot"}
$python=Get-Command python -ErrorAction SilentlyContinue
if(-not $python){throw 'python.exe was not found in PATH.'}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Write-Host 'RAVEN OVERRIDE TOKEN PERSISTENCE PROBE - READ ONLY'
Write-Host 'Mines native Raven override IDs/tokens and searches the current save ring.'
Write-Host 'No save/progression/game writes.'
Write-Host ''

$lines=& $python.Source $Probe --game-root $GameRoot --save-root $SaveRoot --output $json 2>&1 |
    ForEach-Object {"$_"; Write-Host "$_"}
$code=$LASTEXITCODE
$lines|Set-Content -LiteralPath $log -Encoding UTF8
if($code-ne 0){Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Value "exit_code=$code" -Encoding UTF8}

Invoke-Git @('add','-f','--',$relativeDir)
$message=if($code-eq 0){"research(v0.10.5): probe Raven override-token persistence $stamp"}else{"research(v0.10.5): archive failed Raven override-token persistence probe $stamp"}
Invoke-Git @('commit','-m',$message,'--',$relativeDir)
Invoke-Git @('push','origin',$ExpectedBranch)
$head=(& git -C $RepoRoot rev-parse HEAD).Trim()

if($code-ne 0){throw "Raven override-token persistence probe failed; evidence pushed in $head"}

Write-Host ''
Write-Host "RAVEN_OVERRIDE_TOKEN_PERSISTENCE_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
