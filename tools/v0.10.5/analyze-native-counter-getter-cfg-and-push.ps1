[CmdletBinding()]
param([string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar')
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$branch='codex/all-collectibles-production-research'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ((& git -C $repo branch --show-current).Trim() -ne $branch){throw 'Wrong branch'}
$staged=@(& git -C $repo diff --cached --name-only)
if($LASTEXITCODE-ne 0){throw 'Unable to inspect staged changes'}
if($staged.Count-gt 0){throw "Refusing staged changes: $($staged -join ', ')"}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/source-scans/native-counter-getter-cfg-$stamp"
$out=Join-Path $repo ($rel -replace '/',[IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $out | Out-Null
$json=Join-Path $out 'report.json'; $txt=Join-Path $out 'report.txt'; $log=Join-Path $out 'console-log.txt'
$script=Join-Path $PSScriptRoot 'analyze-native-counter-getter-cfg.py'
$lines=& python $script --game-root $GameRoot --output-json $json --output-text $txt 2>&1 | ForEach-Object {"$_";Write-Host "$_"}
$code=$LASTEXITCODE; $lines|Set-Content -LiteralPath $log -Encoding UTF8
if($code-ne 0){Set-Content -LiteralPath (Join-Path $out 'error.txt') -Value "exit_code=$code" -Encoding UTF8}
& git -C $repo add -f -- $rel
if($LASTEXITCODE-ne 0){throw 'git add failed'}
$msg=if($code-eq 0){"research(v0.10.5): analyze native counter getter CFG $stamp"}else{"research(v0.10.5): archive failed native counter getter CFG $stamp"}
& git -C $repo commit -m $msg -- $rel | Out-Host
if($LASTEXITCODE-ne 0){throw 'git commit failed'}
& git -C $repo push origin $branch | Out-Host
if($LASTEXITCODE-ne 0){throw 'git push failed'}
if($code-ne 0){throw 'Native counter getter CFG analysis failed; evidence pushed'}
Write-Host "NATIVE_COUNTER_GETTER_CFG_PUSHED $((& git -C $repo rev-parse HEAD).Trim())" -ForegroundColor Green
