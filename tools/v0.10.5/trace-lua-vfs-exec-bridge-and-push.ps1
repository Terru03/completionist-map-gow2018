[CmdletBinding()]
param([string]$Exe='G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside the Completionist Map repository.'}
Set-Location $RepoRoot
$Probe=Join-Path $RepoRoot 'tools\v0.10.5\trace-lua-vfs-exec-bridge.py'
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir="archive/field-logs/source-scans/lua-vfs-exec-bridge-$stamp"
$outDir=Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$json=Join-Path $outDir 'report.json'
$text=Join-Path $outDir 'report.txt'
$log=Join-Path $outDir 'console-log.txt'

function Invoke-Git {
    param([string[]]$GitArgs)
    & git -C $RepoRoot @GitArgs | Out-Host
    if($LASTEXITCODE -ne 0){throw "git $($GitArgs -join ' ') failed"}
}

$branch=(& git -C $RepoRoot branch --show-current).Trim()
if($branch -ne $ExpectedBranch){throw "Wrong branch '$branch'; expected '$ExpectedBranch'."}
$staged=@(& git -C $RepoRoot diff --cached --name-only)
if($staged.Count -gt 0){throw "Refusing pre-existing staged changes: $($staged -join ', ')"}
if(@(Get-Process -ErrorAction SilentlyContinue | Where-Object{$_.ProcessName -in @('GoW','GodOfWar')}).Count -gt 0){
    throw 'Close God of War before this static trace.'
}
foreach($p in @($Probe,$Exe)){
    if(-not(Test-Path -LiteralPath $p -PathType Leaf)){throw "Required file missing: $p"}
}
$python=Get-Command python -ErrorAction SilentlyContinue
if(-not $python){throw 'python.exe was not found in PATH.'}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Write-Host 'LUA VFSEXEC BRIDGE TRACE - STATIC / READ ONLY'
$lines=& $python.Source $Probe --exe $Exe --output-json $json --output-text $text 2>&1 | ForEach-Object{"$_"; Write-Host "$_"}
$code=$LASTEXITCODE
$lines | Set-Content -LiteralPath $log -Encoding UTF8
if($code -ne 0){
    Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Value "exit_code=$code" -Encoding UTF8
}
Invoke-Git @('add','-f','--',$relativeDir)
$msg=if($code -eq 0){"research(v0.10.5): trace Lua VFSExec bridge $stamp"}else{"research(v0.10.5): archive failed Lua VFSExec bridge $stamp"}
Invoke-Git @('commit','-m',$msg,'--',$relativeDir)
Invoke-Git @('push','origin',$ExpectedBranch)
$head=(& git -C $RepoRoot rev-parse HEAD).Trim()
if($code -ne 0){throw "Trace failed; evidence pushed in $head"}
Write-Host ''
Write-Host "LUA_VFS_EXEC_BRIDGE_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
