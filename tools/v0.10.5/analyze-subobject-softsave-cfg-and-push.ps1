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
$rel="archive/field-logs/source-scans/subobject-softsave-cfg-$stamp"
$out=Join-Path $repo $rel;New-Item -ItemType Directory -Force -Path $out|Out-Null
$json=Join-Path $out 'report.json';$txt=Join-Path $out 'report.txt';$log=Join-Path $out 'console-log.txt'
try{
  $lines=& python (Join-Path $repo 'tools\v0.10.5\analyze-subobject-softsave-cfg.py') --game-root $GameRoot --output-json $json --output-text $txt 2>&1 | ForEach-Object {"$_";Write-Host "$_"}
  $code=$LASTEXITCODE;$lines|Set-Content $log -Encoding UTF8
  if($code-ne 0){throw "analysis failed exit=$code"}
}catch{
  $_.Exception.ToString()|Set-Content (Join-Path $out 'error.txt') -Encoding UTF8
}finally{
  & git add -f -- $rel
  & git diff --cached --quiet -- $rel
  if($LASTEXITCODE -eq 1){
    $failed=Test-Path (Join-Path $out 'error.txt')
    $msg=if($failed){"research(v0.10.5): archive failed SubObject SoftSave CFG $stamp"}else{"research(v0.10.5): archive SubObject SoftSave CFG $stamp"}
    & git commit -m $msg -- $rel | Out-Host
    if($LASTEXITCODE -eq 0){& git push origin $branch | Out-Host}
  }
}
if(Test-Path (Join-Path $out 'error.txt')){throw 'SubObject SoftSave CFG failed; evidence pushed'}
Write-Host "SUBOBJECT_SOFTSAVE_CFG_PUSHED $((& git rev-parse HEAD).Trim())" -ForegroundColor Green
