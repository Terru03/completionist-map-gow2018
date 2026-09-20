[CmdletBinding()]
param([string]$GameRoot='G:\\SteamLibrary\\steamapps\\common\\GodOfWar')
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim();if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside repository.'};Set-Location $RepoRoot
if(((& git branch --show-current).Trim())-ne $ExpectedBranch){throw 'Wrong branch.'}
if(@(& git diff --cached --name-only).Count-gt 0){throw 'Refusing pre-existing staged changes.'}
if(@(Get-Process -ErrorAction SilentlyContinue|Where-Object{$_.ProcessName -in @('GoW','GodOfWar')}).Count-gt 0){throw 'Close God of War before this static trace.'}
$IndexName='gow-caebcb027980.sqlite';$Parent=Split-Path -Parent $RepoRoot
$roots=@((Join-Path $RepoRoot '.research-index'),(Join-Path $Parent 'completionist-map-gow2018-all-collectibles-production-research\.research-index'))
$IndexRoot=$roots|Where-Object{Test-Path -LiteralPath (Join-Path $_ $IndexName)-PathType Leaf}|Select-Object -First 1
if(-not $IndexRoot){throw 'Research index not found.'}
$Db=Join-Path $IndexRoot $IndexName;$Cap=Join-Path $IndexRoot 'python-packages'
$Probe=Join-Path $RepoRoot 'tools\v0.10.5\trace-staged-wad-parallel-channels.py';$Exe=Join-Path $GameRoot 'GoW.exe'
foreach($p in @($Probe,$Exe,$Db)){if(-not(Test-Path -LiteralPath $p -PathType Leaf)){throw "Missing: $p"}}
$Python=Get-Command python -ErrorAction Stop
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss');$relative="archive/field-logs/source-scans/staged-wad-parallel-channels-$stamp";$out=Join-Path $RepoRoot ($relative-replace'/',[IO.Path]::DirectorySeparatorChar);New-Item -ItemType Directory -Force -Path $out|Out-Null
$json=Join-Path $out 'report.json';$txt=Join-Path $out 'report.txt';$log=Join-Path $out 'console-log.txt'
$lines=& $Python.Source $Probe --exe $Exe --db $Db --capstone-path $Cap --output-json $json --output-text $txt 2>&1|ForEach-Object{"$_";Write-Host "$_"};$code=$LASTEXITCODE;$lines|Set-Content $log -Encoding UTF8
if($code-ne 0){Set-Content (Join-Path $out 'error.txt') "exit_code=$code"}
& git add -f -- $relative;if($LASTEXITCODE){throw 'git add failed'}
$msg=if($code-eq 0){"research(v0.10.5): trace staged WAD parallel channels $stamp"}else{"research(v0.10.5): archive failed staged WAD parallel trace $stamp"}
& git commit -m $msg -- $relative;if($LASTEXITCODE){throw 'git commit failed'};& git push origin $ExpectedBranch;if($LASTEXITCODE){throw 'git push failed'}
$head=(& git rev-parse HEAD).Trim();if($code-ne 0){throw "Trace failed; evidence pushed in $head"};Write-Host "STAGED_WAD_PARALLEL_CHANNEL_TRACE_PUSHED $head" -ForegroundColor Green
