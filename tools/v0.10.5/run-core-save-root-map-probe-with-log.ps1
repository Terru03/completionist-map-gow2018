[CmdletBinding()]
param([string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar')

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside the Completionist Map repository.'}
Set-Location $RepoRoot

$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir="archive/field-logs/runtime-captures/core-save-root-map-$stamp"
$outDir=Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$pristineCore=Join-Path $GameRoot 'mods\lua_source\gameart\scripts\libraries\core\save.lua'
$coreOverride=Join-Path $GameRoot 'mods\lua\gameart\scripts\libraries\core\save.lua'
$mapMenu=Join-Path $GameRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$probe=Join-Path $RepoRoot 'tools\v0.10.5\core-save-root-map-probe.lua'
$loaderLog=Join-Path $GameRoot 'mods\loader_log.txt'
$exe=Join-Path $GameRoot 'GoW.exe'

$coreBackup=Join-Path $env:TEMP "completionist-core-save-$stamp.bak"
$mapBackup=Join-Path $env:TEMP "completionist-mapmenu-$stamp.bak"
$coreExisted=$false
$restored=$false
$gameLaunched=$false
$probeOutputFound=$false
$published=$false
$transcriptStarted=$false

function Stop-LocalTranscript {
  if($script:transcriptStarted){
    Stop-Transcript | Out-Null
    $script:transcriptStarted=$false
  }
}

function Restore-Files {
  if($script:restored){return}
  if(Test-Path -LiteralPath $mapBackup -PathType Leaf){
    [IO.File]::WriteAllBytes($mapMenu,[IO.File]::ReadAllBytes($mapBackup))
  }
  if($script:coreExisted){
    if(Test-Path -LiteralPath $coreBackup -PathType Leaf){
      [IO.File]::WriteAllBytes($coreOverride,[IO.File]::ReadAllBytes($coreBackup))
    }
  } else {
    Remove-Item -LiteralPath $coreOverride -Force -ErrorAction SilentlyContinue
  }
  $script:restored=$true
}

function Wait-ForConfirmedGameExit {
  while($true){
    Read-Host 'After God of War has fully exited, press Enter to capture the log and restore the temporary Lua overrides' | Out-Null
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
    "files_restored=$($script:restored.ToString().ToLowerInvariant())"
    'probe_read_only=true'
    'probe_save_writes=false'
    'probe_progression_writes=false'
    'core_save_accessor_read_only=true'
  ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

  & git add -f -- $relativeDir
  if($LASTEXITCODE-ne 0){throw 'git add failed.'}
  & git diff --cached --quiet -- $relativeDir
  if($LASTEXITCODE-eq 0){return}
  if($LASTEXITCODE-ne 1){throw 'Unable to inspect staged capture.'}
  & git commit -m "research(v0.10.5): capture core.save root from map $stamp" -- $relativeDir | Out-Host
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
  foreach($path in @($pristineCore,$mapMenu,$probe,$exe)){
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "Required file missing: $path"}
  }

  $coreDir=Split-Path -Parent $coreOverride
  New-Item -ItemType Directory -Force -Path $coreDir | Out-Null

  $coreExisted=Test-Path -LiteralPath $coreOverride -PathType Leaf
  if($coreExisted){[IO.File]::WriteAllBytes($coreBackup,[IO.File]::ReadAllBytes($coreOverride))}
  [IO.File]::WriteAllBytes($mapBackup,[IO.File]::ReadAllBytes($mapMenu))

  $pristineHash=(Get-FileHash -LiteralPath $pristineCore -Algorithm SHA256).Hash.ToLowerInvariant()
  $mapBeforeHash=(Get-FileHash -LiteralPath $mapMenu -Algorithm SHA256).Hash.ToLowerInvariant()

  $coreText=[IO.File]::ReadAllText($pristineCore,[Text.Encoding]::UTF8)
  if($coreText.Contains('PeekSaveStateRoot')){throw 'Pristine core.save unexpectedly already exports PeekSaveStateRoot.'}
  $needle='  Restore = Restore'
  $occurrences=([regex]::Matches($coreText,[regex]::Escape($needle))).Count
  if($occurrences-ne 1){throw "Expected one core.save Restore export, found $occurrences."}
  $replacement=@'
  Restore = Restore,
  PeekSaveStateRoot = function()
    return object_savestate
  end
'@
  $patchedCore=$coreText.Replace($needle,$replacement.TrimEnd())
  [IO.File]::WriteAllText($coreOverride,$patchedCore,[Text.UTF8Encoding]::new($false))

  $mapBytes=[IO.File]::ReadAllBytes($mapMenu)
  $mapText=[Text.Encoding]::UTF8.GetString($mapBytes)
  if($mapText.Contains('BEGIN COMPLETIONIST CORE SAVE ROOT MAP PROBE')){
    throw 'mapmenu.lua already contains the core.save root probe marker.'
  }
  $probeText=[IO.File]::ReadAllText($probe,[Text.Encoding]::UTF8)
  $append=[Text.Encoding]::UTF8.GetBytes([Environment]::NewLine+$probeText)
  $combined=New-Object byte[] ($mapBytes.Length+$append.Length)
  [Array]::Copy($mapBytes,0,$combined,0,$mapBytes.Length)
  [Array]::Copy($append,0,$combined,$mapBytes.Length,$append.Length)
  [IO.File]::WriteAllBytes($mapMenu,$combined)

  $coreInstalledHash=(Get-FileHash -LiteralPath $coreOverride -Algorithm SHA256).Hash.ToLowerInvariant()
  $mapInstalledHash=(Get-FileHash -LiteralPath $mapMenu -Algorithm SHA256).Hash.ToLowerInvariant()
  @(
    "pristine_core_save_sha256=$pristineHash"
    "temporary_core_override_sha256=$coreInstalledHash"
    "mapmenu_before_sha256=$mapBeforeHash"
    "mapmenu_probe_installed_sha256=$mapInstalledHash"
    "core_override_preexisted=$($coreExisted.ToString().ToLowerInvariant())"
    "pristine_core_path=$pristineCore"
    "temporary_core_override_path=$coreOverride"
    "mapmenu_path=$mapMenu"
    'accessor=PeekSaveStateRoot'
    'accessor_behavior=return_object_savestate_only'
    'probe_read_only=true'
    'probe_save_writes=false'
    'probe_progression_writes=false'
  ) | Set-Content -LiteralPath (Join-Path $outDir 'installed-file-hashes.txt') -Encoding UTF8

  Write-Host ''
  Write-Host 'Temporary read-only core.save accessor + map probe installed.' -ForegroundColor Green
  Write-Host 'Load your almost-done save, then OPEN THE MAP ONCE where you spawn.' -ForegroundColor Cyan
  Write-Host 'Do not fast travel and do not go to Veithurgard for this test.' -ForegroundColor Cyan
  Write-Host 'After the map has been open for a few seconds, close the game completely.' -ForegroundColor Cyan
  Write-Host 'Then return to this PowerShell window and press Enter.' -ForegroundColor Cyan
  Write-Host ''

  Start-Process -FilePath $exe -WorkingDirectory $GameRoot | Out-Null
  $gameLaunched=$true
  Wait-ForConfirmedGameExit

  if(Test-Path -LiteralPath $loaderLog -PathType Leaf){
    Copy-Item -LiteralPath $loaderLog -Destination (Join-Path $outDir 'loader_log.txt') -Force
    $lines=@(Select-String -LiteralPath $loaderLog -SimpleMatch '[CompletionistCoreSaveRootProbe]' | ForEach-Object {$_.Line})
    if($lines.Count-gt 0){
      $probeOutputFound=$true
      $lines | Set-Content -LiteralPath (Join-Path $outDir 'probe-extract.txt') -Encoding UTF8
      Write-Host "Captured $($lines.Count) core.save root probe lines."
    } else {
      'NO_COMPLETIONIST_CORE_SAVE_ROOT_PROBE_LINES_FOUND' | Set-Content -LiteralPath (Join-Path $outDir 'probe-extract.txt') -Encoding UTF8
    }
  } else {
    'LOADER_LOG_NOT_FOUND' | Set-Content -LiteralPath (Join-Path $outDir 'probe-extract.txt') -Encoding UTF8
  }

  Restore-Files

  $mapAfterHash=(Get-FileHash -LiteralPath $mapMenu -Algorithm SHA256).Hash.ToLowerInvariant()
  $coreRestore='deleted'
  if($coreExisted){
    $coreRestore=(Get-FileHash -LiteralPath $coreOverride -Algorithm SHA256).Hash.ToLowerInvariant()
  } elseif(Test-Path -LiteralPath $coreOverride){
    throw 'Temporary core.save override still exists after restore.'
  }
  @(
    "mapmenu_before_sha256=$mapBeforeHash"
    "mapmenu_after_restore_sha256=$mapAfterHash"
    "mapmenu_exact_restore=$($mapAfterHash -eq $mapBeforeHash)"
    "core_override_preexisted=$($coreExisted.ToString().ToLowerInvariant())"
    "core_override_after_restore=$coreRestore"
  ) | Set-Content -LiteralPath (Join-Path $outDir 'restore-verification.txt') -Encoding UTF8
  if($mapAfterHash-ne $mapBeforeHash){throw 'mapmenu.lua restore hash mismatch.'}

  if($probeOutputFound){
    Publish-Capture 'CORE_SAVE_ROOT_MAP_CAPTURED'
    Write-Host 'CORE_SAVE_ROOT_MAP_CAPTURED_AND_PUSHED' -ForegroundColor Green
  } else {
    Publish-Capture 'CORE_SAVE_ROOT_MAP_NO_OUTPUT'
    Write-Host 'CORE_SAVE_ROOT_MAP_NO_OUTPUT_PUSHED' -ForegroundColor Yellow
  }
}
catch {
  try {$_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8} catch {}
  try {Restore-Files} catch {}
  try {Publish-Capture 'CORE_SAVE_ROOT_MAP_FAILED'} catch {}
  Write-Host "CORE_SAVE_ROOT_MAP_PROBE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}
finally {
  try {Restore-Files} catch {}
  if(Test-Path -LiteralPath $coreBackup){Remove-Item -LiteralPath $coreBackup -Force -ErrorAction SilentlyContinue}
  if(Test-Path -LiteralPath $mapBackup){Remove-Item -LiteralPath $mapBackup -Force -ErrorAction SilentlyContinue}
  Stop-LocalTranscript
}
