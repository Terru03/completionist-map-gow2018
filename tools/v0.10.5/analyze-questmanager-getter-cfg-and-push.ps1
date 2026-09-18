[CmdletBinding()]
param([string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar')
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$branch='codex/all-collectibles-production-research'
$repo=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($repo)){throw 'Not inside repository'}
Set-Location $repo
if((& git branch --show-current).Trim() -ne $branch){throw 'Wrong branch'}
$staged=@(& git diff --cached --name-only); if($staged.Count -gt 0){throw "Pre-existing staged changes: $($staged -join ', ')"}
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/source-scans/questmanager-getter-cfg-$stamp"
$out=Join-Path $repo $rel
New-Item -ItemType Directory -Force -Path $out|Out-Null
$script=Join-Path $repo 'tools\v0.10.5\analyze-questmanager-getter-cfg.py'
$json=Join-Path $out 'report.json'; $txt=Join-Path $out 'report.txt'; $log=Join-Path $out 'console-log.txt'
try{
  $lines=& python $script --game-root $GameRoot --output-json $json --output-text $txt 2>&1 | ForEach-Object {"$_";Write-Host "$_"}
  $lines|Set-Content -LiteralPath $log -Encoding UTF8
}catch{
  $_.Exception.ToString()|Set-Content -LiteralPath (Join-Path $out 'error.txt') -Encoding UTF8
  throw
}finally{
  & git add -f -- $rel
  & git diff --cached --quiet -- $rel
  if($LASTEXITCODE -eq 1){
    $failed=Test-Path (Join-Path $out 'error.txt')
    $msg=if($failed){"research(v0.10.5): archive failed QuestManager getter CFG $stamp"}else{"research(v0.10.5): archive QuestManager getter CFG $stamp"}
    & git commit -m $msg -- $rel | Out-Host
    if($LASTEXITCODE -eq 0){& git push origin $branch | Out-Host}
  }
}
if(Test-Path (Join-Path $out 'error.txt')){throw 'QuestManager getter CFG failed; evidence pushed'}
Write-Host "QUESTMANAGER_GETTER_CFG_PUSHED $((& git rev-parse HEAD).Trim())" -ForegroundColor Green
