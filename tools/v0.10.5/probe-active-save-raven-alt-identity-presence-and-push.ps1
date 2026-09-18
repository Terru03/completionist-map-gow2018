[CmdletBinding()]
param([string]$SaveRoot="$HOME\Saved Games\God of War")
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$branch='codex/all-collectibles-production-research'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ((& git -C $repo branch --show-current).Trim() -ne $branch){throw "Wrong branch"}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/save-forensics/active-raven-alt-identity-presence-$stamp"
$out=Join-Path $repo ($rel -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $out | Out-Null
$json=Join-Path $out 'report.json'
$log=Join-Path $out 'console-log.txt'
$script=Join-Path $PSScriptRoot 'probe-active-save-raven-alt-identity-presence.py'
$lines=& python $script --save-root $SaveRoot --output $json 2>&1 | ForEach-Object {"$_"; Write-Host "$_"}
$code=$LASTEXITCODE
$lines|Set-Content -LiteralPath $log -Encoding UTF8
if($code-ne 0){Set-Content -LiteralPath (Join-Path $out 'error.txt') -Value "exit_code=$code" -Encoding UTF8}
& git -C $repo add -f -- $rel
if($LASTEXITCODE-ne 0){throw 'git add failed'}
$msg=if($code-eq 0){"research(v0.10.5): probe alternate Raven save identities $stamp"}else{"research(v0.10.5): archive failed alternate Raven identity probe $stamp"}
& git -C $repo commit -m $msg -- $rel | Out-Host
if($LASTEXITCODE-ne 0){throw 'git commit failed'}
& git -C $repo push origin $branch | Out-Host
if($LASTEXITCODE-ne 0){throw 'git push failed'}
if($code-ne 0){throw 'Alternate Raven identity probe failed; evidence pushed'}
Write-Host "ACTIVE_RAVEN_ALT_IDENTITY_PRESENCE_PUSHED $((& git -C $repo rev-parse HEAD).Trim())"
