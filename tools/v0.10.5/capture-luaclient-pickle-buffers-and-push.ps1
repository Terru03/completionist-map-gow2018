[CmdletBinding()]
param()
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$branch='codex/all-collectibles-production-research'
$repo=(& git rev-parse --show-toplevel 2>$null).Trim()
if(-not $repo){throw 'Not inside repository'};Set-Location $repo
if((& git branch --show-current).Trim()-ne $branch){throw 'Wrong branch'}
if(-not(Get-Process -Name GoW -ErrorAction SilentlyContinue)){throw 'God of War must still be running for this read-only capture'}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/runtime-captures/luaclient-pickle-buffers-$stamp";$out=Join-Path $repo $rel
New-Item -ItemType Directory -Force -Path $out|Out-Null
$ids=Join-Path $repo 'catalogue\odins-ravens-save-identities.json'
& python '.\tools\v0.10.5\capture-luaclient-pickle-buffers.py' --identities $ids --output-dir $out 2>&1 | Tee-Object -FilePath (Join-Path $out 'console-log.txt') | Out-Host
$code=$LASTEXITCODE
if($code-ne 0){ "capture_exit=$code" | Set-Content (Join-Path $out 'error.txt') -Encoding UTF8 }
git add -f -- $rel
git commit -m "research(v0.10.5): capture live LuaClient pickle buffers $stamp" -- $rel | Out-Host
if($LASTEXITCODE-ne 0){throw 'git commit failed'}
git push origin $branch | Out-Host
if($LASTEXITCODE-ne 0){throw 'git push failed'}
if($code-ne 0){throw "LuaClient pickle-buffer capture failed; evidence pushed (exit=$code)"}
Write-Host "LUACLIENT_PICKLE_BUFFERS_PUSHED $((& git rev-parse HEAD).Trim())" -ForegroundColor Green
