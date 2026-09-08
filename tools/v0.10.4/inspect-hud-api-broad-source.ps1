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
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
  throw "God of War root not found: $GameRoot"
}

$reportRel = 'archive/field-logs/completionist-v104-hud-api-broad-source.txt'
$reportPath = Join-Path $repo ($reportRel -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath) | Out-Null

# Read-only source recovery scan. The earlier v0.7.6 inventory saw 118 UI Lua
# files and real GetInstancedChildObject/GetChildSubObject usage. The current
# injected source tree contains only the two files we modify. Search the game
# tree plus the repo for any retained/extracted source copy before guessing API
# signatures at runtime.
$patterns = [ordered]@{
  'GetInstancedChildObject'       = 'GetInstancedChildObject'
  'GetChildSubObject'             = 'GetChildSubObject'
  'ShowInstancedChildObject'      = 'ShowInstancedChildObject'
  'AlphaFadeInstancedChildObject' = 'AlphaFadeInstancedChildObject'
  'FindSingleGOByName'            = 'FindSingleGOByName'
  'FindGOsByName'                 = 'FindGOsByName'
  'SetMaterialSwap'               = 'SetMaterialSwap'
  'Compass.ShowMarker'            = 'Compass.ShowMarker'
  'UI.WorldUIRender'              = 'UI.WorldUIRender'
  'UI.SendEvent'                  = 'UI.SendEvent'
}

$roots = @(
  [pscustomobject]@{ Label = 'GAME'; Path = (Resolve-Path -LiteralPath $GameRoot).Path; Extensions = @('.lua') },
  [pscustomobject]@{ Label = 'REPO'; Path = (Resolve-Path -LiteralPath $repo).Path; Extensions = @('.lua', '.txt', '.md') }
)

# Skip Git object storage and generated dependency/cache trees; they cannot be
# the extracted stock Lua source we are trying to recover.
$skipParts = @(
  "$([IO.Path]::DirectorySeparatorChar).git$([IO.Path]::DirectorySeparatorChar)",
  "$([IO.Path]::DirectorySeparatorChar)node_modules$([IO.Path]::DirectorySeparatorChar)",
  "$([IO.Path]::DirectorySeparatorChar)__pycache__$([IO.Path]::DirectorySeparatorChar)"
)

$allFiles = New-Object System.Collections.Generic.List[object]
foreach ($r in $roots) {
  Get-ChildItem -LiteralPath $r.Path -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    $full = $_.FullName
    foreach ($skip in $skipParts) {
      if ($full.IndexOf($skip, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return }
    }
    if ($r.Extensions -contains $_.Extension.ToLowerInvariant()) {
      $allFiles.Add([pscustomobject]@{ Root = $r.Label; RootPath = $r.Path; File = $_ })
    }
  }
}

$sb = New-Object Text.StringBuilder
[void]$sb.AppendLine('Completionist Map v0.10.4 HUD API broad source recovery scan')
[void]$sb.AppendLine(('Generated UTC: {0:o}' -f [DateTime]::UtcNow))
[void]$sb.AppendLine("Game root: $GameRoot")
[void]$sb.AppendLine("Repo root: $repo")
[void]$sb.AppendLine('Game files written: false')
[void]$sb.AppendLine('')

foreach ($r in $roots) {
  $count = @($allFiles | Where-Object Root -eq $r.Label).Count
  [void]$sb.AppendLine(("{0} text/source files scanned: {1}" -f $r.Label, $count))
}

# Inventory candidate gameart/ui/scripts roots and how many Lua files each has.
[void]$sb.AppendLine('')
[void]$sb.AppendLine('DISCOVERED UI SCRIPT ROOTS')
$uiRoots = @{}
foreach ($entry in ($allFiles | Where-Object { $_.File.Extension -ieq '.lua' })) {
  $full = $entry.File.FullName
  $needle = "$([IO.Path]::DirectorySeparatorChar)gameart$([IO.Path]::DirectorySeparatorChar)ui$([IO.Path]::DirectorySeparatorChar)scripts$([IO.Path]::DirectorySeparatorChar)"
  $idx = $full.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase)
  if ($idx -ge 0) {
    $rootEnd = $idx + $needle.Length - 1
    $uiRoot = $full.Substring(0, $rootEnd)
    if (-not $uiRoots.ContainsKey($uiRoot)) { $uiRoots[$uiRoot] = 0 }
    $uiRoots[$uiRoot]++
  }
}
if ($uiRoots.Count -eq 0) {
  [void]$sb.AppendLine('<none>')
} else {
  foreach ($kv in ($uiRoots.GetEnumerator() | Sort-Object Value -Descending)) {
    [void]$sb.AppendLine(("{0} | lua_files={1}" -f $kv.Key, $kv.Value))
  }
}

$matchesByPattern = [ordered]@{}
foreach ($name in $patterns.Keys) { $matchesByPattern[$name] = New-Object System.Collections.Generic.List[object] }

foreach ($entry in $allFiles) {
  $file = $entry.File
  try {
    $lines = [IO.File]::ReadAllLines($file.FullName)
  } catch {
    continue
  }
  for ($i = 0; $i -lt $lines.Length; $i++) {
    $line = $lines[$i]
    foreach ($name in $patterns.Keys) {
      if ($line.IndexOf($patterns[$name], [StringComparison]::Ordinal) -ge 0) {
        $matchesByPattern[$name].Add([pscustomobject]@{
          Root = $entry.Root
          Path = $file.FullName
          Line = $i + 1
          Lines = $lines
          Index = $i
        })
      }
    }
  }
}

[void]$sb.AppendLine('')
[void]$sb.AppendLine('MATCH COUNTS')
foreach ($name in $patterns.Keys) {
  [void]$sb.AppendLine(("{0}: {1}" -f $name, $matchesByPattern[$name].Count))
}

# Put the two key APIs first and include generous context so a real call shape
# can be copied exactly instead of inferred.
foreach ($name in $patterns.Keys) {
  [void]$sb.AppendLine('')
  [void]$sb.AppendLine(("=== {0} ===" -f $name))
  $hits = $matchesByPattern[$name]
  if ($hits.Count -eq 0) {
    [void]$sb.AppendLine('<no matches>')
    continue
  }

  $ordinal = 0
  foreach ($hit in $hits) {
    $ordinal++
    # Avoid making the report enormous for generic methods; preserve all calls
    # for the two unknown APIs and cap secondary evidence at 40 contexts each.
    if ($name -notin @('GetInstancedChildObject','GetChildSubObject','ShowInstancedChildObject','AlphaFadeInstancedChildObject') -and $ordinal -gt 40) {
      [void]$sb.AppendLine(("... {0} additional matches omitted" -f ($hits.Count - 40)))
      break
    }

    $relative = $hit.Path
    if ($hit.Root -eq 'GAME') {
      $relative = $hit.Path.Substring($GameRoot.Length).TrimStart('\')
    } elseif ($hit.Root -eq 'REPO') {
      $relative = $hit.Path.Substring($repo.Length).TrimStart('\')
    }
    [void]$sb.AppendLine(("-- [{0}] {1}:{2}" -f $hit.Root, $relative, $hit.Line))
    $from = [Math]::Max(0, $hit.Index - 4)
    $to = [Math]::Min($hit.Lines.Length - 1, $hit.Index + 4)
    for ($j = $from; $j -le $to; $j++) {
      $mark = if ($j -eq $hit.Index) { '>' } else { ' ' }
      [void]$sb.AppendLine(("{0}{1,6}: {2}" -f $mark, ($j + 1), $hit.Lines[$j]))
    }
  }
}

[void]$sb.AppendLine('')
[void]$sb.AppendLine('INTERPRETATION GATE')
[void]$sb.AppendLine('Use an instanced-child API in a runtime Raven probe only if this report recovers at least one real Lua call context that establishes its argument shape. A count from a historical inventory alone is not enough. If no real call context is recovered, do not guess the signature.')

[IO.File]::WriteAllText($reportPath, $sb.ToString(), (New-Object Text.UTF8Encoding($false)))
Write-Host "Wrote read-only report: $reportPath"

# Commit only the report generated by this tool. It never writes beneath the
# game root.
git add -- $reportRel
if (-not (git diff --cached --quiet)) {
  git commit -m 'Archive broad HUD API source recovery scan'
  git push
  if ($LASTEXITCODE -ne 0) { throw 'git push failed' }
} else {
  Write-Host 'Report unchanged; nothing to commit.'
}