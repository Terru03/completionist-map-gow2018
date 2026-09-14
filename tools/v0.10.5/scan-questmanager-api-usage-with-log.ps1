param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$repo = (Get-Location).Path
$gameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
$expectedBranch = 'codex/all-collectibles-production-research'
$branch = (git branch --show-current).Trim()
if ($branch -ne $expectedBranch) { throw "Expected branch $expectedBranch, got $branch" }

$roots = @(
  (Join-Path $gameRoot 'mods\lua_source'),
  (Join-Path $gameRoot 'mods\lua')
) | Where-Object { Test-Path $_ }
if (-not $roots) { throw 'No Lua source roots found under game mods directory.' }

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outRel = "archive/field-logs/source-scans/questmanager-api-usage-$timestamp"
$outDir = Join-Path $repo $outRel
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$report = Join-Path $outDir 'questmanager-methods.txt'
$result = Join-Path $outDir 'result.txt'
Start-Transcript -Path $console -Force | Out-Null

try {
  Write-Host '=== Completionist Map QuestManager API usage scan ==='
  Write-Host "Repository: $repo"
  Write-Host "Game root: $gameRoot"
  Write-Host 'Read-only Lua source scan. Game/save/progression are not written and the game is not launched.'

  $files = New-Object System.Collections.Generic.List[System.IO.FileInfo]
  foreach ($root in $roots) {
    Get-ChildItem -LiteralPath $root -Recurse -File -Filter '*.lua' -ErrorAction SilentlyContinue | ForEach-Object { [void]$files.Add($_) }
  }

  $methodCounts = @{}
  $methodSamples = @{}
  $regex = [regex]'(?<![A-Za-z0-9_])(?:game\.)?QuestManager\.([A-Za-z_][A-Za-z0-9_]*)'

  foreach ($file in $files) {
    $lines = [System.IO.File]::ReadAllLines($file.FullName)
    for ($i = 0; $i -lt $lines.Length; $i++) {
      $matches = $regex.Matches($lines[$i])
      foreach ($m in $matches) {
        $method = $m.Groups[1].Value
        if (-not $methodCounts.ContainsKey($method)) {
          $methodCounts[$method] = 0
          $methodSamples[$method] = New-Object System.Collections.Generic.List[string]
        }
        $methodCounts[$method]++
        if ($methodSamples[$method].Count -lt 8) {
          $rel = $file.FullName
          foreach ($root in $roots) {
            if ($file.FullName.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
              $rel = (Split-Path $root -Leaf) + '\' + $file.FullName.Substring($root.Length).TrimStart('\')
              break
            }
          }
          [void]$methodSamples[$method].Add("${rel}:$($i+1): $($lines[$i].Trim())")
        }
      }
    }
  }

  $ordered = @($methodCounts.Keys | Sort-Object)
  $sb = New-Object System.Text.StringBuilder
  [void]$sb.AppendLine('Completionist Map - QuestManager methods observed in shipped/live Lua')
  [void]$sb.AppendLine("timestamp=$timestamp")
  [void]$sb.AppendLine("lua_files_scanned=$($files.Count)")
  [void]$sb.AppendLine("unique_methods=$($ordered.Count)")
  [void]$sb.AppendLine('')
  foreach ($method in $ordered) {
    [void]$sb.AppendLine("METHOD $method count=$($methodCounts[$method])")
    foreach ($sample in $methodSamples[$method]) { [void]$sb.AppendLine("  $sample") }
    [void]$sb.AppendLine('')
  }
  [System.IO.File]::WriteAllText($report, $sb.ToString(), [System.Text.UTF8Encoding]::new($false))

  $resultLines = @(
    'result=SCAN_PASSED',
    "timestamp=$(Get-Date -Format o)",
    "branch=$branch",
    "lua_files_scanned=$($files.Count)",
    "unique_methods=$($ordered.Count)",
    'active_save_opened=false',
    'game_written=false',
    'save_or_progression_written=false',
    'game_launched=false'
  )
  foreach ($method in $ordered) { $resultLines += "count.$method=$($methodCounts[$method])" }
  [System.IO.File]::WriteAllLines($result, $resultLines, [System.Text.UTF8Encoding]::new($false))

  Write-Host "QUESTMANAGER_API_SCAN_COMPLETED files=$($files.Count) methods=$($ordered.Count)"
  Write-Host "Output: $outRel"
}
finally {
  Stop-Transcript | Out-Null
}

git add -- $outRel
git commit -m "Archive QuestManager API usage $timestamp"
git push origin HEAD:$expectedBranch
Write-Host 'SCAN_PASSED_AND_PUSHED'
