[CmdletBinding()]
param([string]$GameRoot='G:\SteamLibrary\steamapps\common\GodOfWar')

$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside the Completionist Map repository.'}
Set-Location $RepoRoot

$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir="archive/field-logs/runtime-captures/subobject-api-map-$stamp"
$outDir=Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$mapMenu=Join-Path $GameRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$probe=Join-Path $RepoRoot 'tools\v0.10.5\subobject-api-map-probe.lua'
$loaderLog=Join-Path $GameRoot 'mods\loader_log.txt'
$exe=Join-Path $GameRoot 'GoW.exe'
$backup=Join-Path $env:TEMP "completionist-mapmenu-subobject-api-$stamp.bak"

$restored=$false
$published=$false
$transcriptStarted=$false
$gameLaunched=$false
$probeOutputFound=$false

function Stop-LocalTranscript {
  if($script:transcriptStarted){
    Stop-Transcript | Out-Null
    $script:transcriptStarted=$false
  }
}

function Restore-Target {
  if($script:restored){return}
  if(Test-Path -LiteralPath $backup -PathType Leaf){
    [IO.File]::WriteAllBytes($mapMenu,[IO.File]::ReadAllBytes($backup))
    $script:restored=$true
  }
}

function Wait-ForConfirmedGameExit {
  while($true){
    Read-Host 'After God of War has fully exited, press Enter to capture the log and restore mapmenu.lua' | Out-Null
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
    "mapmenu_restored=$($script:restored.ToString().ToLowerInvariant())"
    'probe_read_only=true'
    'probe_invokes_subobject_functions=false'
    'probe_save_writes=false'
    'probe_progression_writes=false'
  ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

  & git add -f -- $relativeDir
  if($LASTEXITCODE-ne 0){throw 'git add failed.'}
  & git diff --cached --quiet -- $relativeDir
  if($LASTEXITCODE-eq 0){return}
  if($LASTEXITCODE-ne 1){throw 'Unable to inspect staged capture.'}
  & git commit -m "research(v0.10.5): inventory SubObject runtime API $stamp" -- $relativeDir | Out-Host
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
  foreach($path in @($mapMenu,$probe,$exe)){
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "Required file missing: $path"}
  }

  $original=[IO.File]::ReadAllBytes($mapMenu)
  [IO.File]::WriteAllBytes($backup,$original)
  $beforeHash=(Get-FileHash -LiteralPath $mapMenu -Algorithm SHA256).Hash.ToLowerInvariant()

  $text=[Text.Encoding]::UTF8.GetString($original)
  if($text.Contains('BEGIN COMPLETIONIST SUBOBJECT API INVENTORY PROBE')){
    throw 'mapmenu.lua already contains the SubObject API probe marker.'
  }
  $probeText=[IO.File]::ReadAllText($probe,[Text.Encoding]::UTF8)
  $append=[Text.Encoding]::UTF8.GetBytes([Environment]::NewLine+$probeText)
  $combined=New-Object byte[] ($original.Length+$append.Length)
  [Array]::Copy($original,0,$combined,0,$original.Length)
  [Array]::Copy($append,0,$combined,$original.Length,$append.Length)
  [IO.File]::WriteAllBytes($mapMenu,$combined)

  $installedHash=(Get-FileHash -LiteralPath $mapMenu -Algorithm SHA256).Hash.ToLowerInvariant()
  @(
    "mapmenu_before_sha256=$beforeHash"
    "mapmenu_probe_installed_sha256=$installedHash"
    "mapmenu_path=$mapMenu"
    "probe_path=$probe"
    'probe_read_only=true'
    'probe_invokes_subobject_functions=false'
  ) | Set-Content -LiteralPath (Join-Path $outDir 'installed-file-hashes.txt') -Encoding UTF8

  Write-Host ''
  Write-Host 'Temporary read-only game.SubObject API inventory installed.' -ForegroundColor Green
  Write-Host 'Load your almost-done save and OPEN THE MAP ONCE where you spawn.' -ForegroundColor Cyan
  Write-Host 'No travel or Raven interaction is needed. Then quit God of War completely.' -ForegroundColor Cyan
  Write-Host 'Return here and press Enter.' -ForegroundColor Cyan
  Write-Host ''

  Start-Process -FilePath $exe -WorkingDirectory $GameRoot | Out-Null
  $gameLaunched=$true
  Wait-ForConfirmedGameExit

  if(Test-Path -LiteralPath $loaderLog -PathType Leaf){
    Copy-Item -LiteralPath $loaderLog -Destination (Join-Path $outDir 'loader_log.txt') -Force
    $lines=@(Select-String -LiteralPath $loaderLog -SimpleMatch '[CompletionistSubObjectApiProbe]' | ForEach-Object {$_.Line})
    if($lines.Count-gt 0){
      $probeOutputFound=$true
      $lines | Set-Content -LiteralPath (Join-Path $outDir 'probe-extract.txt') -Encoding UTF8
      Write-Host "Captured $($lines.Count) SubObject API probe lines."
    } else {
      'NO_COMPLETIONIST_SUBOBJECT_API_PROBE_LINES_FOUND' | Set-Content -LiteralPath (Join-Path $outDir 'probe-extract.txt') -Encoding UTF8
    }
  } else {
    'LOADER_LOG_NOT_FOUND' | Set-Content -LiteralPath (Join-Path $outDir 'probe-extract.txt') -Encoding UTF8
  }

  Restore-Target
  $afterHash=(Get-FileHash -LiteralPath $mapMenu -Algorithm SHA256).Hash.ToLowerInvariant()
  @(
    "mapmenu_before_sha256=$beforeHash"
    "mapmenu_after_restore_sha256=$afterHash"
    "exact_restore=$($afterHash -eq $beforeHash)"
  ) | Set-Content -LiteralPath (Join-Path $outDir 'restore-verification.txt') -Encoding UTF8
  if($afterHash-ne $beforeHash){throw 'mapmenu.lua restore hash mismatch.'}

  if($probeOutputFound){
    Publish-Capture 'SUBOBJECT_API_MAP_CAPTURED'
    Write-Host 'SUBOBJECT_API_MAP_CAPTURED_AND_PUSHED' -ForegroundColor Green
  } else {
    Publish-Capture 'SUBOBJECT_API_MAP_NO_OUTPUT'
    Write-Host 'SUBOBJECT_API_MAP_NO_OUTPUT_PUSHED' -ForegroundColor Yellow
  }
}
catch {
  try {$_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8} catch {}
  try {Restore-Target} catch {}
  try {Publish-Capture 'SUBOBJECT_API_MAP_FAILED'} catch {}
  Write-Host "SUBOBJECT_API_MAP_PROBE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}
finally {
  try {Restore-Target} catch {}
  if(Test-Path -LiteralPath $backup){Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue}
  Stop-LocalTranscript
}
