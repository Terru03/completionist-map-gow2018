param([string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar')
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$branch='codex/all-collectibles-production-research'
$repo=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($repo)){throw 'Not inside repository'}
Set-Location $repo
if((& git branch --show-current).Trim() -ne $branch){throw 'Wrong branch'}
$staged=@(& git diff --cached --name-only); if($staged.Count -gt 0){throw "Pre-existing staged changes: $($staged -join ', ')"}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$rel="archive/field-logs/runtime-captures/questmanager-native-closure-$stamp"
$out=Join-Path $repo $rel
New-Item -ItemType Directory -Force -Path $out|Out-Null
$map=Join-Path $GameRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$probe=Join-Path $repo 'tools\v0.10.5\generic-counter-runtime-probe.lua'
$py=Join-Path $repo 'tools\v0.10.5\capture-questmanager-native-closures.py'
$loader=Join-Path $GameRoot 'mods\loader_log.txt'
$exe=Join-Path $GameRoot 'GoW.exe'
$bak=Join-Path $env:TEMP "completionist-qm-$stamp.bak"
$restored=$false
function Restore-Map {
  if($script:restored){return}
  if(Test-Path $bak){[IO.File]::WriteAllBytes($map,[IO.File]::ReadAllBytes($bak));$script:restored=$true}
}
try{
  if(Get-Process -Name GoW -ErrorAction SilentlyContinue){throw 'Close GoW before starting'}
  foreach($p in @($map,$probe,$py,$exe)){if(-not(Test-Path $p)){throw "Missing: $p"}}
  [IO.File]::WriteAllBytes($bak,[IO.File]::ReadAllBytes($map))
  $before=(Get-FileHash $map -Algorithm SHA256).Hash.ToLowerInvariant()
  $orig=[IO.File]::ReadAllBytes($map)
  $probeText=[IO.File]::ReadAllText($probe)
  $append=[Text.Encoding]::UTF8.GetBytes([Environment]::NewLine+$probeText.Replace("`n",[Environment]::NewLine))
  $all=New-Object byte[] ($orig.Length+$append.Length)
  [Array]::Copy($orig,0,$all,0,$orig.Length);[Array]::Copy($append,0,$all,$orig.Length,$append.Length)
  [IO.File]::WriteAllBytes($map,$all)
  Start-Process -FilePath $exe -WorkingDirectory $GameRoot|Out-Null
  Read-Host 'Load the almost-done save, open the world map, move the cursor once, Alt-Tab here while GoW is STILL RUNNING, then press Enter'|Out-Null
  if(-not(Get-Process -Name GoW -ErrorAction SilentlyContinue)){throw 'GoW is no longer running'}
  if(-not(Test-Path $loader)){throw 'loader_log.txt missing'}
  Copy-Item $loader (Join-Path $out 'loader_log.txt') -Force
  $lines=@(Select-String -LiteralPath $loader -SimpleMatch '[CompletionistCounterProbe]'|ForEach-Object {$_.Line})
  $lines|Set-Content (Join-Path $out 'probe-extract.txt') -Encoding UTF8
  $closure=@($lines|Where-Object {$_ -match 'QM_CLOSURE name=.* type=function tostring=function:'})
  if($closure.Count -lt 4){throw "Expected QuestManager closure lines; found $($closure.Count)"}
  & python $py --loader-log $loader --output (Join-Path $out 'closure-report.json') 2>&1 | Tee-Object -FilePath (Join-Path $out 'closure-console.txt') | Out-Host
  if($LASTEXITCODE -ne 0){throw 'Closure memory capture failed'}
  Restore-Map
  $after=(Get-FileHash $map -Algorithm SHA256).Hash.ToLowerInvariant()
  @("before=$before","after=$after","exact_restore=$($before -eq $after)")|Set-Content (Join-Path $out 'restore-verification.txt') -Encoding UTF8
  if($before -ne $after){throw 'mapmenu.lua restore mismatch'}
  & git add -f -- $rel
  & git commit -m "research(v0.10.5): capture QuestManager native closures $stamp" -- $rel | Out-Host
  if($LASTEXITCODE -ne 0){throw 'git commit failed'}
  & git push origin $branch | Out-Host
  if($LASTEXITCODE -ne 0){throw 'git push failed'}
  Write-Host "QM_NATIVE_CLOSURE_CAPTURE_PUSHED $((& git rev-parse HEAD).Trim())" -ForegroundColor Green
  Write-Host 'Capture complete; you can close God of War.' -ForegroundColor Cyan
}catch{
  $err = $_.Exception.ToString()
  try { $err | Set-Content -LiteralPath (Join-Path $out 'error.txt') -Encoding UTF8 } catch {}
  try { Restore-Map } catch {}
  try {
    & git add -f -- $rel
    if($LASTEXITCODE -eq 0){
      & git diff --cached --quiet -- $rel
      if($LASTEXITCODE -eq 1){
        & git commit -m "research(v0.10.5): archive failed QuestManager native closure capture $stamp" -- $rel | Out-Host
        if($LASTEXITCODE -eq 0){ & git push origin $branch | Out-Host }
      }
    }
  } catch {}
  Write-Host "QM_NATIVE_CLOSURE_CAPTURE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}finally{
  try{Restore-Map}catch{}
  if(Test-Path $bak){Remove-Item $bak -Force -ErrorAction SilentlyContinue}
}
