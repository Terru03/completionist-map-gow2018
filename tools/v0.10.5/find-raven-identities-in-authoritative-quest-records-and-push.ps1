[CmdletBinding()]
param()
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$branch='codex/all-collectibles-production-research'
$repo=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($repo)){throw 'Not inside repository'}
Set-Location $repo
if((& git branch --show-current).Trim() -ne $branch){throw 'Wrong branch'}
$src=Get-ChildItem '.\archive\field-logs\runtime-captures\raven-authoritative-quest-records-*\report.json' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if(-not $src){throw 'No authoritative Raven quest-record report found'}
$ids=Join-Path $repo 'catalogue\odins-ravens-save-identities.json'
if(-not(Test-Path $ids)){throw 'Raven save identity catalogue missing'}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/runtime-captures/raven-quest-graph-exact-identity-search-$stamp"
$out=Join-Path $repo $rel; New-Item -ItemType Directory -Force -Path $out|Out-Null
$json=Join-Path $out 'report.json'; $log=Join-Path $out 'console-log.txt'
& python (Join-Path $repo 'tools\v0.10.5\find-raven-identities-in-authoritative-quest-records.py') --quest-report $src.FullName --identities $ids --output $json 2>&1 | Tee-Object -FilePath $log | Out-Host
if($LASTEXITCODE-ne 0){throw 'identity search failed'}
& git add -f -- $rel
& git commit -m "research(v0.10.5): search Raven identities in authoritative quest graph $stamp" -- $rel | Out-Host
if($LASTEXITCODE-ne 0){throw 'git commit failed'}
& git push origin $branch | Out-Host
if($LASTEXITCODE-ne 0){throw 'git push failed'}
Write-Host "RAVEN_QUEST_GRAPH_IDENTITY_SEARCH_PUSHED $((& git rev-parse HEAD).Trim())" -ForegroundColor Green
