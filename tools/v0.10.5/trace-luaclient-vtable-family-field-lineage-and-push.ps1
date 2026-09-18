[CmdletBinding()]
param([string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar')

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$branch='codex/all-collectibles-production-research'
$repo=(& git rev-parse --show-toplevel 2>$null).Trim()
if(-not $repo){throw 'Not inside repository'}
Set-Location $repo
if((& git branch --show-current).Trim()-ne $branch){throw "Wrong branch. Expected $branch"}

$exe=Join-Path $GameRoot 'GoW.exe'
$db=Join-Path $repo '.research-index\gow-caebcb027980.sqlite'
if(-not(Test-Path $exe)){throw "GoW.exe missing: $exe"}
if(-not(Test-Path $db)){throw "Research index missing: $db"}

$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/source-scans/luaclient-vtable-family-field-lineage-$stamp"
$out=Join-Path $repo $rel
New-Item -ItemType Directory -Force -Path $out | Out-Null

& python '.\tools\v0.10.5\trace-luaclient-vtable-family-field-lineage.py' `
    --exe $exe `
    --db $db `
    --output-json (Join-Path $out 'report.json') `
    --output-text (Join-Path $out 'report.txt') 2>&1 |
    Tee-Object -FilePath (Join-Path $out 'console-log.txt') |
    Out-Host
if($LASTEXITCODE-ne 0){throw 'LuaClient vtable-family field-lineage trace failed'}

git add -f -- $rel
git commit -m "research(v0.10.5): trace LuaClient vtable family field lineage $stamp" -- $rel | Out-Host
if($LASTEXITCODE-ne 0){throw 'git commit failed'}

git push origin $branch | Out-Host
if($LASTEXITCODE-ne 0){throw 'git push failed'}

Write-Host "LUACLIENT_VTABLE_FAMILY_FIELD_LINEAGE_PUSHED $((& git rev-parse HEAD).Trim())" -ForegroundColor Green
