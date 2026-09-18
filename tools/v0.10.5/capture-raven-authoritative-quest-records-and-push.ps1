[CmdletBinding()]
param([string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar')
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$branch='codex/all-collectibles-production-research'
$repo=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($repo)){throw 'Not inside repository'}
Set-Location $repo
if((& git branch --show-current).Trim() -ne $branch){throw 'Wrong branch'}
$staged=@(& git diff --cached --name-only); if($staged.Count -gt 0){throw "Pre-existing staged changes: $($staged -join ', ')"}
$exe=Join-Path $GameRoot 'GoW.exe'; if(-not(Test-Path $exe)){throw "GoW.exe missing: $exe"}
if(-not(Get-Process -Name GoW -ErrorAction SilentlyContinue)){Start-Process -FilePath $exe -WorkingDirectory $GameRoot|Out-Null}
Read-Host 'Load the almost-done save and wait until normal gameplay is fully loaded. Keep GoW running, Alt-Tab here, then press Enter for the read-only quest-record capture'|Out-Null
if(-not(Get-Process -Name GoW -ErrorAction SilentlyContinue)){throw 'GoW is not running'}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/runtime-captures/raven-authoritative-quest-records-$stamp"
$out=Join-Path $repo $rel; New-Item -ItemType Directory -Force -Path $out|Out-Null
$json=Join-Path $out 'report.json'; $log=Join-Path $out 'console-log.txt'
try{
  $lines=& python (Join-Path $repo 'tools\v0.10.5\capture-raven-authoritative-quest-records.py') --output $json 2>&1 | ForEach-Object {"$_";Write-Host "$_"}
  $code=$LASTEXITCODE; $lines|Set-Content $log -Encoding UTF8
  if($code-ne 0){throw "capture failed exit=$code"}
}catch{
  $_.Exception.ToString()|Set-Content (Join-Path $out 'error.txt') -Encoding UTF8
}finally{
  & git add -f -- $rel
  & git diff --cached --quiet -- $rel
  if($LASTEXITCODE -eq 1){
    $failed=Test-Path (Join-Path $out 'error.txt')
    $msg=if($failed){"research(v0.10.5): archive failed Raven authoritative quest records $stamp"}else{"research(v0.10.5): capture Raven authoritative quest records $stamp"}
    & git commit -m $msg -- $rel | Out-Host
    if($LASTEXITCODE -eq 0){& git push origin $branch | Out-Host}
  }
}
if(Test-Path (Join-Path $out 'error.txt')){throw 'Quest-record capture failed; evidence pushed'}
Write-Host "RAVEN_AUTHORITATIVE_QUEST_RECORDS_PUSHED $((& git rev-parse HEAD).Trim())" -ForegroundColor Green
Write-Host 'Capture complete; you can close God of War.' -ForegroundColor Cyan
