[CmdletBinding()]
param([string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar')
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$branch='codex/all-collectibles-production-research';$repo=(& git rev-parse --show-toplevel 2>$null).Trim()
if(-not $repo){throw 'Not inside repository'};Set-Location $repo
if((& git branch --show-current).Trim()-ne $branch){throw 'Wrong branch'}
$exe=Join-Path $GameRoot 'GoW.exe';$db=Join-Path $repo '.research-index\gow-caebcb027980.sqlite'
if(-not(Test-Path $exe)){throw "GoW.exe missing: $exe"};if(-not(Test-Path $db)){throw "Research index missing: $db"}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/source-scans/alternate-restore-helper-$stamp";$out=Join-Path $repo $rel
New-Item -ItemType Directory -Force -Path $out|Out-Null
& python '.\tools\v0.10.5\trace-alternate-custom-userdata-restore-helper.py' --exe $exe --db $db --output-json (Join-Path $out 'report.json') --output-text (Join-Path $out 'report.txt') 2>&1 | Tee-Object -FilePath (Join-Path $out 'console-log.txt') | Out-Host
if($LASTEXITCODE-ne 0){throw 'alternate restore helper trace failed'}
git add -f -- $rel;git commit -m "research(v0.10.5): trace alternate restore helper $stamp" -- $rel;git push origin $branch
if($LASTEXITCODE-ne 0){throw 'push failed'}
Write-Host "ALT_RESTORE_HELPER_TRACE_PUSHED $((& git rev-parse HEAD).Trim())" -ForegroundColor Green
