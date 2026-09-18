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
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/runtime-captures/raven-authoritative-quest-record-summary-$stamp"
$out=Join-Path $repo $rel; New-Item -ItemType Directory -Force -Path $out|Out-Null
$json=Join-Path $out 'summary.json'; $log=Join-Path $out 'console-log.txt'
& python (Join-Path $repo 'tools\v0.10.5\summarize-raven-authoritative-quest-records.py') --input $src.FullName --output $json 2>&1 | Tee-Object -FilePath $log | Out-Host
if($LASTEXITCODE-ne 0){throw 'summary failed'}
& git add -f -- $rel
& git commit -m "research(v0.10.5): summarize authoritative Raven quest records $stamp" -- $rel | Out-Host
if($LASTEXITCODE-ne 0){throw 'git commit failed'}
& git push origin $branch | Out-Host
if($LASTEXITCODE-ne 0){throw 'git push failed'}
Write-Host "RAVEN_QUEST_RECORD_SUMMARY_PUSHED $((& git rev-parse HEAD).Trim())" -ForegroundColor Green
