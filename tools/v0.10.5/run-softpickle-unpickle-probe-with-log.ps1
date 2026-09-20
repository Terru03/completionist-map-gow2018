[CmdletBinding()]
param([string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar')

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$ExpectedBranch='codex/all-ravens-release-candidate'
$ExpectedPristineHash='756b1745c0dc29e65f8010bad608b4e7b92b9e78771cc74903084bd0c38c71ac'

$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside the Completionist Map repository.'}
Set-Location $RepoRoot

$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir="archive/field-logs/runtime-captures/softpickle-unpickle-$stamp"
$outDir=Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$pristine=Join-Path $GameRoot 'mods\lua_source\gameart\scripts\libraries\core\pickle.lua'
$override=Join-Path $GameRoot 'mods\lua\gameart\scripts\libraries\core\pickle.lua'
$snippet=Join-Path $RepoRoot 'tools\v0.10.5\softpickle-unpickle-probe-snippet.lua'
$loaderLog=Join-Path $GameRoot 'mods\loader_log.txt'
$exe=Join-Path $GameRoot 'GoW.exe'

$backup=Join-Path $env:TEMP "completionist-core-pickle-$stamp.bak"
$overrideExisted=$false
$restored=$false
$published=$false
$transcriptStarted=$false
$gameLaunched=$false
$probeOutputFound=$false
$beforeLines=@()
$beforeHash=''

function Stop-LocalTranscript {
  if($script:transcriptStarted){
    Stop-Transcript | Out-Null
    $script:transcriptStarted=$false
  }
}

function Restore-Override {
  if($script:restored){return}
  if($script:overrideExisted){
    if(Test-Path -LiteralPath $backup -PathType Leaf){
      [IO.File]::WriteAllBytes($override,[IO.File]::ReadAllBytes($backup))
    }
  } else {
    Remove-Item -LiteralPath $override -Force -ErrorAction SilentlyContinue
  }
  $script:restored=$true
}

function Wait-ForConfirmedGameExit {
  while($true){
    Read-Host 'After God of War has fully exited, press Enter to capture the log and restore core.pickle.lua' | Out-Null
    $running=@(Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -in @('GoW','GodOfWar')})
    if($running.Count-eq 0){return}
    Write-Host 'God of War is still running. Quit it completely before continuing.' -ForegroundColor Yellow
  }
}

function Publish-Capture([string]$result){
  if($script:published){return}
  $script:published=$true
  Stop-LocalTranscript
  @(
    "result=$result"
    "timestamp=$(Get-Date -Format o)"
    "branch=$ExpectedBranch"
    "game_launched=$($script:gameLaunched.ToString().ToLowerInvariant())"
    "probe_output_found=$($script:probeOutputFound.ToString().ToLowerInvariant())"
    "override_restored=$($script:restored.ToString().ToLowerInvariant())"
    'probe_read_only=true'
    'original_unpickle_called=true'
    'save_writes=false'
    'progression_writes=false'
    'streaming_writes=false'
  ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

  & git add -f -- $relativeDir
  if($LASTEXITCODE-ne 0){throw 'git add failed.'}
  & git diff --cached --quiet -- $relativeDir
  if($LASTEXITCODE-eq 0){return}
  if($LASTEXITCODE-ne 1){throw 'Unable to inspect staged capture.'}
  & git commit -m "research(v0.10.5): capture SoftPickle Unpickle $stamp" -- $relativeDir | Out-Host
  if($LASTEXITCODE-ne 0){throw 'git commit failed.'}
  & git push origin "HEAD:$ExpectedBranch" | Out-Host
  if($LASTEXITCODE-ne 0){throw 'git push failed.'}
}

try {
  Start-Transcript -LiteralPath (Join-Path $outDir 'console-log.txt') -Force | Out-Null
  $transcriptStarted=$true

  $branch=(& git branch --show-current).Trim()
  if($branch-ne $ExpectedBranch){throw "Wrong branch '$branch'; expected '$ExpectedBranch'."}
  $staged=@(& git diff --cached --name-only)
  if($LASTEXITCODE-ne 0){throw 'Unable to inspect staged changes.'}
  if($staged.Count-gt 0){throw "Refusing pre-existing staged changes: $($staged -join ', ')"}

  if(@(Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -in @('GoW','GodOfWar')}).Count-gt 0){
    throw 'God of War is already running. Close it first.'
  }
  foreach($path in @($pristine,$snippet,$exe)){
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "Required file missing: $path"}
  }

  $pristineHash=(Get-FileHash -LiteralPath $pristine -Algorithm SHA256).Hash.ToLowerInvariant()
  if($pristineHash-ne $ExpectedPristineHash){
    throw "Unexpected pristine core.pickle.lua SHA256: $pristineHash"
  }

  $overrideDir=Split-Path -Parent $override
  New-Item -ItemType Directory -Force -Path $overrideDir | Out-Null
  $overrideExisted=Test-Path -LiteralPath $override -PathType Leaf
  if($overrideExisted){
    [IO.File]::WriteAllBytes($backup,[IO.File]::ReadAllBytes($override))
  }

  $source=[IO.File]::ReadAllText($pristine,[Text.Encoding]::UTF8)
  $probe=[IO.File]::ReadAllText($snippet,[Text.Encoding]::UTF8)

  $marker='return {'
  $markerIndex=$source.LastIndexOf($marker,[StringComparison]::Ordinal)
  if($markerIndex-lt 0){throw 'Unable to find final return table in pristine core.pickle.lua.'}
  if($source.Contains('CompletionistProbeUnpickle')){throw 'Pristine core.pickle.lua unexpectedly already contains probe code.'}

  $patched=$source.Insert($markerIndex,$probe+[Environment]::NewLine)
  $needle='  Unpickle = unpickle,'
  $count=([regex]::Matches($patched,[regex]::Escape($needle))).Count
  if($count-ne 1){throw "Expected exactly one Unpickle export, found $count."}
  $patched=$patched.Replace($needle,'  Unpickle = CompletionistProbeUnpickle,')

  [IO.File]::WriteAllText($override,$patched,[Text.UTF8Encoding]::new($false))
  $overrideHash=(Get-FileHash -LiteralPath $override -Algorithm SHA256).Hash.ToLowerInvariant()

  @(
    "pristine_sha256=$pristineHash"
    "temporary_override_sha256=$overrideHash"
    "override_preexisted=$($overrideExisted.ToString().ToLowerInvariant())"
    "pristine_path=$pristine"
    "override_path=$override"
    "snippet_path=$snippet"
    'original_unpickle_called_before_inspection=true'
    'probe_read_only=true'
    'save_writes=false'
    'progression_writes=false'
  ) | Set-Content -LiteralPath (Join-Path $outDir 'installed-file-hashes.txt') -Encoding UTF8

  if(Test-Path -LiteralPath $loaderLog -PathType Leaf){
    $beforeLines=@(Get-Content -LiteralPath $loaderLog)
    $beforeHash=(Get-FileHash -LiteralPath $loaderLog -Algorithm SHA256).Hash.ToLowerInvariant()
  }

  Write-Host ''
  Write-Host 'Temporary read-only core.pickle Unpickle probe installed.' -ForegroundColor Green
  Write-Host 'Load your almost-done save and stay where the save spawns you.' -ForegroundColor Cyan
  Write-Host 'Do NOT fast travel and do NOT go to Veithurgard.' -ForegroundColor Cyan
  Write-Host 'Once the save has fully loaded, wait a few seconds, then quit God of War completely.' -ForegroundColor Cyan
  Write-Host 'Return here and press Enter.' -ForegroundColor Cyan
  Write-Host ''

  Start-Process -FilePath $exe -WorkingDirectory $GameRoot | Out-Null
  $gameLaunched=$true
  Wait-ForConfirmedGameExit

  if(Test-Path -LiteralPath $loaderLog -PathType Leaf){
    Copy-Item -LiteralPath $loaderLog -Destination (Join-Path $outDir 'loader_log.txt') -Force
    $afterLines=@(Get-Content -LiteralPath $loaderLog)
    $afterHash=(Get-FileHash -LiteralPath $loaderLog -Algorithm SHA256).Hash.ToLowerInvariant()

    $prefixMatches=$beforeLines.Count-le $afterLines.Count
    if($prefixMatches){
      for($i=0;$i-lt $beforeLines.Count;$i++){
        if($beforeLines[$i]-cne $afterLines[$i]){$prefixMatches=$false;break}
      }
    }
    $fresh=$afterLines
    $mode='overwritten'
    if($prefixMatches-and $beforeLines.Count-gt 0){
      $fresh=@($afterLines|Select-Object -Skip $beforeLines.Count)
      $mode='appended'
    }
    @(
      "before_sha256=$beforeHash"
      "after_sha256=$afterHash"
      "before_lines=$($beforeLines.Count)"
      "after_lines=$($afterLines.Count)"
      "fresh_lines=$($fresh.Count)"
      "mode=$mode"
      "changed=$($afterHash-ne $beforeHash)"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'loader-log-freshness.txt') -Encoding UTF8

    $lines=@($fresh|Select-String -SimpleMatch '[CompletionistSoftPickleProbe]'|ForEach-Object {$_.Line})
    if($lines.Count-gt 0){
      $probeOutputFound=$true
      $lines|Set-Content -LiteralPath (Join-Path $outDir 'probe-extract.txt') -Encoding UTF8
      Write-Host "Captured $($lines.Count) SoftPickle probe lines."
    } else {
      'NO_COMPLETIONIST_SOFTPICKLE_PROBE_LINES_FOUND'|Set-Content -LiteralPath (Join-Path $outDir 'probe-extract.txt') -Encoding UTF8
    }
  } else {
    'LOADER_LOG_NOT_FOUND'|Set-Content -LiteralPath (Join-Path $outDir 'probe-extract.txt') -Encoding UTF8
  }

  Restore-Override

  if($overrideExisted){
    $afterOverrideHash=(Get-FileHash -LiteralPath $override -Algorithm SHA256).Hash.ToLowerInvariant()
    $backupHash=(Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant()
    $exact=$afterOverrideHash-eq $backupHash
  } else {
    $afterOverrideHash='deleted'
    $backupHash='n/a'
    $exact=-not(Test-Path -LiteralPath $override)
  }
  @(
    "override_preexisted=$($overrideExisted.ToString().ToLowerInvariant())"
    "override_after_restore=$afterOverrideHash"
    "backup_sha256=$backupHash"
    "exact_restore=$($exact.ToString().ToLowerInvariant())"
  ) | Set-Content -LiteralPath (Join-Path $outDir 'restore-verification.txt') -Encoding UTF8
  if(-not $exact){throw 'core.pickle.lua override restore verification failed.'}

  if($probeOutputFound){
    Publish-Capture 'SOFTPICKLE_UNPICKLE_CAPTURED'
    Write-Host 'SOFTPICKLE_UNPICKLE_CAPTURED_AND_PUSHED' -ForegroundColor Green
  } else {
    Publish-Capture 'SOFTPICKLE_UNPICKLE_NO_OUTPUT'
    Write-Host 'SOFTPICKLE_UNPICKLE_NO_OUTPUT_PUSHED' -ForegroundColor Yellow
  }
}
catch {
  try {$_.Exception.ToString()|Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8} catch {}
  try {Restore-Override} catch {}
  try {Publish-Capture 'SOFTPICKLE_UNPICKLE_FAILED'} catch {}
  Write-Host "SOFTPICKLE_UNPICKLE_PROBE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}
finally {
  try {Restore-Override} catch {}
  if(Test-Path -LiteralPath $backup){Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue}
  Stop-LocalTranscript
}
