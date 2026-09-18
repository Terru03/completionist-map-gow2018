[CmdletBinding()]
param([string]$SaveRoot="$HOME\Saved Games\God of War")
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$branch='codex/all-collectibles-production-research'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ((& git -C $repo branch --show-current).Trim() -ne $branch){throw 'Wrong branch'}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/save-forensics/active-save-tree-raven-scan-$stamp"
$out=Join-Path $repo ($rel -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $out | Out-Null
$json=Join-Path $out 'report.json'; $log=Join-Path $out 'console-log.txt'
$script=Join-Path $PSScriptRoot 'scan-active-save-tree-for-raven-identities.py'
$lines=& python $script --save-root $SaveRoot --output $json 2>&1 | %{"$_";Write-Host "$_"}
$code=$LASTEXITCODE; $lines|Set-Content $log -Encoding UTF8
if($code-ne 0){Set-Content (Join-Path $out 'error.txt') "exit_code=$code" -Encoding UTF8}
& git -C $repo add -f -- $rel
$msg=if($code-eq 0){"research(v0.10.5): scan full active save tree for Ravens $stamp"}else{"research(v0.10.5): archive failed active save tree Raven scan $stamp"}
& git -C $repo commit -m $msg -- $rel | Out-Host; if($LASTEXITCODE-ne 0){throw 'git commit failed'}
& git -C $repo push origin $branch | Out-Host; if($LASTEXITCODE-ne 0){throw 'git push failed'}
if($code-ne 0){throw 'Active save tree scan failed; evidence pushed'}
Write-Host "ACTIVE_SAVE_TREE_RAVEN_SCAN_PUSHED $((& git -C $repo rev-parse HEAD).Trim())"
