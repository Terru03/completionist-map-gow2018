param(
  [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (git rev-parse --show-toplevel 2>$null).Trim()
if (-not $repo) { throw 'Run this from the completionist-map-gow2018 repository.' }
$branch = (git branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
  throw "Expected branch codex/v104-raven-hud-research, got '$branch'."
}

$sourceCandidates = @(
  (Join-Path $GameRoot 'mods\lua_source\gameart\ui\scripts'),
  (Join-Path $repo 'dist\gowlua-src\gameart\ui\scripts')
)

$sourceRoot = $null
foreach ($candidate in $sourceCandidates) {
  if (Test-Path -LiteralPath $candidate -PathType Container) {
    $count = @(Get-ChildItem -LiteralPath $candidate -Recurse -File -Filter '*.lua' -ErrorAction SilentlyContinue).Count
    if ($count -ge 100) {
      $sourceRoot = (Resolve-Path -LiteralPath $candidate).Path
      break
    }
  }
}
if ($null -eq $sourceRoot) {
  throw 'Could not find a recovered stock UI Lua tree with at least 100 Lua files.'
}

$reportRel = 'archive/field-logs/completionist-v104-stock-compass-renderer-source.txt'
$reportPath = Join-Path $repo ($reportRel -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath) | Out-Null

$allLua = @(Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Filter '*.lua' -ErrorAction Stop)
$needles = @(
  'game.Compass',
  'Compass.ShowMarker',
  'Compass.HideMarker',
  'FindMarkersByIconClass',
  'COMPASS_MARKER',
  'ShowOnCompass',
  'WorldUIRender',
  'SetMaterialSwap',
  'FindSingleGOByName',
  'compass_base',
  'Compass_Base',
  'compass_radius',
  'Compass_Radius'
)

$rows = New-Object System.Collections.Generic.List[object]
foreach ($file in $allLua) {
  $text = $null
  try { $text = [IO.File]::ReadAllText($file.FullName) } catch { continue }
  $score = 0
  $hitNames = New-Object System.Collections.Generic.List[string]
  foreach ($needle in $needles) {
    $idx = $text.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase)
    if ($idx -ge 0) {
      $score++
      $hitNames.Add($needle)
    }
  }
  $nameBoost = if ($file.Name.IndexOf('compass', [StringComparison]::OrdinalIgnoreCase) -ge 0) { 10 } else { 0 }
  $pathBoost = if ($file.FullName.IndexOf('\hud\', [StringComparison]::OrdinalIgnoreCase) -ge 0) { 2 } else { 0 }
  if (($score + $nameBoost) -gt 0) {
    $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart('\')
    $rows.Add([pscustomobject]@{
      File = $file
      Relative = $relative
      Score = $score + $nameBoost + $pathBoost
      Hits = ($hitNames -join ', ')
      IsCompassNamed = ($nameBoost -gt 0)
    })
  }
}

$ranked = @($rows | Sort-Object -Property @{Expression='Score';Descending=$true}, @{Expression='Relative';Descending=$false})
$sb = New-Object Text.StringBuilder
[void]$sb.AppendLine('Completionist Map v0.10.4 stock compass renderer source inspection')
[void]$sb.AppendLine(('Generated UTC: {0:o}' -f [DateTime]::UtcNow))
[void]$sb.AppendLine("Source root: $sourceRoot")
[void]$sb.AppendLine("Lua files scanned: $($allLua.Count)")
[void]$sb.AppendLine('Game files written: false')
[void]$sb.AppendLine('')
[void]$sb.AppendLine('PURPOSE')
[void]$sb.AppendLine('Recover the stock Lua ownership/render path for compass markers before any Raven-specific HUD write test. This report is read-only.')
[void]$sb.AppendLine('')
[void]$sb.AppendLine('RANKED COMPASS-RELATED FILES')
foreach ($row in ($ranked | Select-Object -First 30)) {
  [void]$sb.AppendLine(("score={0} | {1} | {2}" -f $row.Score, $row.Relative, $row.Hits))
}

# Fully archive any file whose filename itself contains "compass". There should
# only be a small number, and exact source is more useful here than another
# guessed API signature.
$compassNamed = @($ranked | Where-Object IsCompassNamed)
[void]$sb.AppendLine('')
[void]$sb.AppendLine("COMPASS-NAMED FILES: $($compassNamed.Count)")
foreach ($row in $compassNamed) {
  [void]$sb.AppendLine('')
  [void]$sb.AppendLine(("===== FULL SOURCE: {0} =====" -f $row.Relative))
  try {
    [void]$sb.AppendLine([IO.File]::ReadAllText($row.File.FullName))
  } catch {
    [void]$sb.AppendLine(("<read failed: {0}>" -f $_.Exception.Message))
  }
}

# For the strongest non-compass-named owners (normally mapmenu/mainhud/etc.),
# include exact contexts around native Compass and renderer calls.
$contextNeedles = @(
  'game.Compass',
  'FindMarkersByIconClass',
  'ShowMarker',
  'HideMarker',
  'WorldUIRender',
  'SetMaterialSwap',
  'compass_base',
  'Compass_Base'
)
$contextRows = @($ranked | Where-Object { -not $_.IsCompassNamed } | Select-Object -First 12)
foreach ($row in $contextRows) {
  $lines = $null
  try { $lines = [IO.File]::ReadAllLines($row.File.FullName) } catch { continue }
  $seen = @{}
  $written = 0
  [void]$sb.AppendLine('')
  [void]$sb.AppendLine(("===== CONTEXTS: {0} =====" -f $row.Relative))
  for ($i = 0; $i -lt $lines.Length; $i++) {
    $line = $lines[$i]
    $matched = $false
    foreach ($needle in $contextNeedles) {
      if ($line.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
        $matched = $true
        break
      }
    }
    if (-not $matched) { continue }
    $bucket = [Math]::Floor($i / 8)
    if ($seen.ContainsKey($bucket)) { continue }
    $seen[$bucket] = $true
    $from = [Math]::Max(0, $i - 6)
    $to = [Math]::Min($lines.Length - 1, $i + 8)
    [void]$sb.AppendLine(("-- around line {0}" -f ($i + 1)))
    for ($j = $from; $j -le $to; $j++) {
      $mark = if ($j -eq $i) { '>' } else { ' ' }
      [void]$sb.AppendLine(("{0}{1,6}: {2}" -f $mark, ($j + 1), $lines[$j]))
    }
    $written++
    if ($written -ge 35) { break }
  }
}

[void]$sb.AppendLine('')
[void]$sb.AppendLine('INTERPRETATION GATE')
[void]$sb.AppendLine('Do not mutate compass_base or shared DockPoint artwork from this report alone. First identify the stock marker-instance owner and whether marker icon material is assigned per instance or through a shared class resource.')

[IO.File]::WriteAllText($reportPath, $sb.ToString(), (New-Object Text.UTF8Encoding($false)))
Write-Host "Wrote read-only report: $reportPath"

git add -- $reportRel
if (-not (git diff --cached --quiet)) {
  git commit -m 'Archive stock compass renderer source inspection'
  if ($LASTEXITCODE -ne 0) { throw 'git commit failed' }
  git push
  if ($LASTEXITCODE -ne 0) { throw 'git push failed' }
} else {
  Write-Host 'Report unchanged; nothing to commit.'
}
