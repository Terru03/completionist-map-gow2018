[CmdletBinding()]
param([string]$SaveRoot="$HOME\Saved Games\God of War")
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$branch='codex/all-collectibles-production-research'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ((& git -C $repo branch --show-current).Trim() -ne $branch){throw 'Wrong branch'}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/save-forensics/active-raven-payload-presence-$stamp"
$out=Join-Path $repo ($rel -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $out | Out-Null
$log=Join-Path $out 'console-log.txt'; $json=Join-Path $out 'report.json'
$lines=& python (Join-Path $PSScriptRoot 'probe-active-save-raven-payload-presence.py') --save-root $SaveRoot --output $json 2>&1 | %{"$_";Write-Host "$_"}
$code=$LASTEXITCODE; $lines|Set-Content $log -Encoding UTF8
if($code-ne 0){Set-Content (Join-Path $out 'error.txt') "exit_code=$code" -Encoding UTF8}
& git -C $repo add -f -- $rel
$msg=if($code-eq 0){"research(v0.10.5): probe active Raven payload presence $stamp"}else{"research(v0.10.5): archive failed Raven payload probe $stamp"}
& git -C $repo commit -m $msg -- $rel | Out-Host; if($LASTEXITCODE-ne 0){throw 'git commit failed'}
& git -C $repo push origin $branch | Out-Host; if($LASTEXITCODE-ne 0){throw 'git push failed'}
if($code-ne 0){throw 'Raven payload presence probe failed; evidence pushed'}
Write-Host "ACTIVE_RAVEN_PAYLOAD_PRESENCE_PUSHED $((& git -C $repo rev-parse HEAD).Trim())"
