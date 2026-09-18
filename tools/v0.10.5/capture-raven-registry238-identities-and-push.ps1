[CmdletBinding()]
param([string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar')
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$branch='codex/all-collectibles-production-research'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ((& git -C $repo branch --show-current).Trim() -ne $branch){throw 'Wrong branch'}
$staged=@(& git -C $repo diff --cached --name-only)
if($LASTEXITCODE-ne 0){throw 'Unable to inspect staged changes'}
if($staged.Count-gt 0){throw "Refusing staged changes: $($staged -join ', ')"}

$exe=Join-Path $GameRoot 'GoW.exe'
if(-not(Test-Path -LiteralPath $exe -PathType Leaf)){throw "GoW.exe missing: $exe"}
$running=@(Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -in @('GoW','GodOfWar')})
if($running.Count-eq 0){
    Start-Process -FilePath $exe -WorkingDirectory $GameRoot | Out-Null
    Write-Host 'God of War launched.' -ForegroundColor Cyan
}
Read-Host 'Load the almost-done save and leave the game running in gameplay. Then Alt-Tab here and press Enter for the read-only registry scan' | Out-Null
$running=@(Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -in @('GoW','GodOfWar')})
if($running.Count-eq 0){throw 'God of War is not running'}

$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/runtime-captures/raven-registry238-$stamp"
$out=Join-Path $repo ($rel -replace '/',[IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $out | Out-Null
$json=Join-Path $out 'report.json'; $log=Join-Path $out 'console-log.txt'
$script=Join-Path $PSScriptRoot 'capture-raven-registry238-identities.py'
$lines=& python $script --output $json 2>&1 | ForEach-Object {"$_";Write-Host "$_"}
$code=$LASTEXITCODE
$lines|Set-Content -LiteralPath $log -Encoding UTF8
if($code-ne 0){Set-Content -LiteralPath (Join-Path $out 'error.txt') -Value "exit_code=$code" -Encoding UTF8}
& git -C $repo add -f -- $rel
if($LASTEXITCODE-ne 0){throw 'git add failed'}
$msg=if($code-eq 0){"research(v0.10.5): capture registry238 Raven identities $stamp"}else{"research(v0.10.5): archive failed registry238 Raven capture $stamp"}
& git -C $repo commit -m $msg -- $rel | Out-Host
if($LASTEXITCODE-ne 0){throw 'git commit failed'}
& git -C $repo push origin $branch | Out-Host
if($LASTEXITCODE-ne 0){throw 'git push failed'}
if($code-ne 0){throw 'Registry238 Raven capture failed; evidence pushed'}
Write-Host "RAVEN_REGISTRY238_CAPTURE_PUSHED $((& git -C $repo rev-parse HEAD).Trim())" -ForegroundColor Green
Write-Host 'The scan is complete. You can now close God of War.' -ForegroundColor Cyan
