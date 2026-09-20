[CmdletBinding()]
param()
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim();if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside the Completionist Map repository.'};Set-Location $RepoRoot
if(((& git branch --show-current).Trim())-ne $ExpectedBranch){throw 'Wrong branch.'}
if(@(& git diff --cached --name-only).Count-gt 0){throw 'Refusing pre-existing staged changes.'}
$Probe=Join-Path $RepoRoot 'tools\v0.10.5\capture-staged-wad-dual-payload-raven-state-readonly.py';if(-not(Test-Path $Probe -PathType Leaf)){throw "Missing probe: $Probe"}
$Python=Get-Command python -ErrorAction Stop
$gow=@(Get-Process -ErrorAction SilentlyContinue|Where-Object{$_.ProcessName -in @('GoW','GodOfWar')});if($gow.Count-ne 1){throw 'Start God of War and load the almost-complete save, then rerun.'}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss');$relative="archive/field-logs/runtime-captures/staged-wad-dual-payload-raven-state-readonly-$stamp";$out=Join-Path $RepoRoot ($relative-replace'/',[IO.Path]::DirectorySeparatorChar);New-Item -ItemType Directory -Force -Path $out|Out-Null
$json=Join-Path $out 'report.json';$txt=Join-Path $out 'report.txt';$log=Join-Path $out 'console-log.txt'
Write-Host 'STAGED WAD DUAL PAYLOAD RAVEN STATE - READ ONLY'
Write-Host 'Keep God of War running on the loaded almost-complete save. No gameplay action is required.'
Write-Host 'Reads only the two proven per-WAD payload descriptors and their shared staged pool.'
Write-Host 'No debugger, no process writes, no save reads/writes, no progression writes.'
$lines=& $Python.Source $Probe --output-json $json --output-text $txt 2>&1|ForEach-Object{"$_";Write-Host "$_"};$code=$LASTEXITCODE;$lines|Set-Content $log -Encoding UTF8
if($code-ne 0){Set-Content (Join-Path $out 'error.txt') "exit_code=$code"}
& git add -f -- $relative;if($LASTEXITCODE){throw 'git add failed'}
$msg=if($code-eq 0){"research(v0.10.5): capture staged WAD dual Raven payloads $stamp"}else{"research(v0.10.5): archive failed staged WAD dual Raven capture $stamp"}
& git commit -m $msg -- $relative;if($LASTEXITCODE){throw 'git commit failed'};& git push origin $ExpectedBranch;if($LASTEXITCODE){throw 'git push failed'}
$head=(& git rev-parse HEAD).Trim();if($code-ne 0){throw "Dual payload capture failed; evidence pushed in $head"};Write-Host "STAGED_WAD_DUAL_RAVEN_PUSHED $head" -ForegroundColor Green
