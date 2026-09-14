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
$outRel = "archive/field-logs/source-scans/persistence-hook-api-usage-$timestamp"
$outDir = Join-Path $repo $outRel
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$report = Join-Path $outDir 'usage-context.txt'
$result = Join-Path $outDir 'result.txt'
Start-Transcript -Path $console -Force | Out-Null

try {
  Write-Host '=== Completionist Map persistence/hook API usage scan ==='
  Write-Host "Repository: $repo"
  Write-Host "Game root: $gameRoot"
  Write-Host 'Read-only Lua source scan. Game/save/progression are not written and the game is not launched.'

  $terms = @(
    'SerializeHook',
    'DebugGetSubObjectEnvironmentRoot',
    'CurrentlyExecutingObject',
    'CurrentlyExecutingSubObject',
    'AddPreProgressHook',
    'AddPostProgressHook',
    'SendHook',
    'RegisterListener',
    'UnregisterListener',
    'EVT_Collectible_Changed',
    'EVT_COUNTER_CHANGE',
    'regionSummaryQuest',
    'Quest_Labor_KillRavens',
    'ravenKilled',
    'SoftSave(thisObj)',
    'IncrementQuestProgress(regionSummaryQuest'
  )

  $files = New-Object System.Collections.Generic.List[System.IO.FileInfo]
  foreach ($root in $roots) {
    Get-ChildItem -LiteralPath $root -Recurse -File -Filter '*.lua' -ErrorAction SilentlyContinue | ForEach-Object { [void]$files.Add($_) }
  }

  $counts = @{}
  foreach ($term in $terms) { $counts[$term] = 0 }
  $totalMatches = 0
  $sb = New-Object System.Text.StringBuilder
  [void]$sb.AppendLine('Completionist Map - persistence/hook API usage contexts')
  [void]$sb.AppendLine("timestamp=$timestamp")
  [void]$sb.AppendLine("lua_files_scanned=$($files.Count)")
  [void]$sb.AppendLine('')

  foreach ($file in $files) {
    $lines = [System.IO.File]::ReadAllLines($file.FullName)
    for ($i = 0; $i -lt $lines.Length; $i++) {
      $matched = New-Object System.Collections.Generic.List[string]
      foreach ($term in $terms) {
        if ($lines[$i].IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
          [void]$matched.Add($term)
          $counts[$term]++
        }
      }
      if ($matched.Count -eq 0) { continue }
      $totalMatches++

      $rel = $file.FullName
      foreach ($root in $roots) {
        if ($file.FullName.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
          $rel = (Split-Path $root -Leaf) + '\' + $file.FullName.Substring($root.Length).TrimStart('\')
          break
        }
      }

      [void]$sb.AppendLine(('=' * 100))
      [void]$sb.AppendLine("FILE $rel")
      [void]$sb.AppendLine("MATCH line=$($i+1) terms=$($matched -join ',')")
      $start = [Math]::Max(0, $i - 14)
      $end = [Math]::Min($lines.Length - 1, $i + 14)
      for ($j = $start; $j -le $end; $j++) {
        $mark = if ($j -eq $i) { '>>' } else { '  ' }
        [void]$sb.AppendLine(('{0} {1,5}: {2}' -f $mark, ($j+1), $lines[$j]))
      }
      [void]$sb.AppendLine('')
    }
  }

  [System.IO.File]::WriteAllText($report, $sb.ToString(), [System.Text.UTF8Encoding]::new($false))

  $resultLines = New-Object System.Collections.Generic.List[string]
  [void]$resultLines.Add('result=SCAN_PASSED')
  [void]$resultLines.Add("timestamp=$(Get-Date -Format o)")
  [void]$resultLines.Add("branch=$branch")
  [void]$resultLines.Add("lua_files_scanned=$($files.Count)")
  [void]$resultLines.Add("matches=$totalMatches")
  foreach ($term in $terms) { [void]$resultLines.Add("count.$term=$($counts[$term])") }
  [void]$resultLines.Add('active_save_opened=false')
  [void]$resultLines.Add('game_written=false')
  [void]$resultLines.Add('save_or_progression_written=false')
  [void]$resultLines.Add('game_launched=false')
  [System.IO.File]::WriteAllLines($result, $resultLines, [System.Text.UTF8Encoding]::new($false))

  Write-Host "PERSISTENCE_HOOK_API_SCAN_COMPLETED files=$($files.Count) matches=$totalMatches"
  Write-Host "Output: $outRel"
}
finally {
  Stop-Transcript | Out-Null
}

git add -- $outRel
git commit -m "Archive persistence hook API usage $timestamp"
git push origin HEAD:$expectedBranch
Write-Host 'SCAN_PASSED_AND_PUSHED'
