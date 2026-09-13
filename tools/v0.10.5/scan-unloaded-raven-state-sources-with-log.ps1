param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-ravens-release-candidate'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/source-scans/unloaded-raven-state-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$matchesPath = Join-Path $logDir 'matches.txt'
$inventoryPath = Join-Path $logDir 'inventory.json'
$precisionPath = Join-Path $logDir 'precisionchallenge-context.txt'

$published = $false
$transcriptStarted = $false

function Invoke-Git([string[]]$Args) {
    $output = & git @Args 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Args -join ' ') failed:`n$($output -join "`n")"
    }
    return @($output)
}

function Publish-Scan([string]$Result) {
    if ($script:published) { return }
    $script:published = $true
    try {
        if ($script:transcriptStarted) {
            Stop-Transcript | Out-Null
            $script:transcriptStarted = $false
        }
        $resultFile = Join-Path $logDir 'result.txt'
        @(
            "result=$Result"
            "timestamp=$(Get-Date -Format o)"
            "branch=$expectedBranch"
            "game_written=false"
            "save_or_progression_written=false"
            "game_launched=false"
            "scan_only=true"
        ) | Set-Content -LiteralPath $resultFile -Encoding UTF8

        & git add -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git add of scan directory failed.' }
        & git diff --cached --quiet -- $relativeLogDir
        if ($LASTEXITCODE -eq 0) { return }
        & git commit -m "Archive unloaded Raven state source scan $stamp" -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git commit of scan directory failed.' }
        & git push origin "HEAD:$expectedBranch"
        if ($LASTEXITCODE -ne 0) { throw 'git push of scan directory failed.' }
    }
    catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map v0.10.5 unloaded Raven state source scan ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) {
        throw "Wrong branch. Expected '$expectedBranch', found '$branch'."
    }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) {
        throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')"
    }

    $game = [IO.Path]::GetFullPath($GameRoot)
    if (-not (Test-Path -LiteralPath $game -PathType Container)) {
        throw "Game root not found: $game"
    }

    # This helper is deliberately read-only with respect to the game. It scans only
    # loose Lua source already present under the game's mods/lua tree.
    $luaRoot = Join-Path $game 'mods\lua'
    if (-not (Test-Path -LiteralPath $luaRoot -PathType Container)) {
        throw "Loose Lua root not found: $luaRoot"
    }

    $luaFiles = @(Get-ChildItem -LiteralPath $luaRoot -Recurse -File -Filter '*.lua' -ErrorAction Stop)
    Write-Host "Loose Lua files: $($luaFiles.Count)"

    $patterns = [ordered]@{
        raven = '(?i)ravenKilled|RegionSummary_[A-Z0-9]+_Raven_Parent|precisionchallenge'
        checkpoint = '(?i)checkpoint|restorecheckpoint|savecheckpoint'
        persistence = '(?i)persist|serializ|deserializ|object.?state|game.?state|save.?state|load.?state'
        identity = '(?i)instance.?guid|instance.?id|object.?guid|\bguid\b'
        lookup = '(?i)(Get|Find|Query|Lookup)[A-Za-z0-9_]*(Object|Instance|State|Checkpoint|Save|Quest)'
        quest = '(?i)(game\.)?[A-Za-z0-9_]*Quest[A-Za-z0-9_]*\s*\('
    }

    $records = New-Object System.Collections.Generic.List[object]
    foreach ($file in $luaFiles) {
        $lines = [IO.File]::ReadAllLines($file.FullName)
        for ($i = 0; $i -lt $lines.Length; $i++) {
            $line = $lines[$i]
            $categories = New-Object System.Collections.Generic.List[string]
            foreach ($entry in $patterns.GetEnumerator()) {
                if ($line -match $entry.Value) { $categories.Add([string]$entry.Key) }
            }
            if ($categories.Count -eq 0) { continue }
            $relative = [IO.Path]::GetRelativePath($luaRoot, $file.FullName)
            $records.Add([pscustomobject]@{
                file = $relative.Replace('\','/')
                line = $i + 1
                categories = @($categories)
                text = $line.Trim()
            })
        }
    }

    $sorted = @($records | Sort-Object file, line)
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($record in $sorted) {
        $out.Add(('{0}:{1}: [{2}] {3}' -f $record.file, $record.line, ($record.categories -join ','), $record.text))
    }
    $out | Set-Content -LiteralPath $matchesPath -Encoding UTF8

    $categoryCounts = [ordered]@{}
    foreach ($key in $patterns.Keys) {
        $categoryCounts[$key] = @($sorted | Where-Object { $_.categories -contains $key }).Count
    }
    $fileHitCounts = @($sorted | Group-Object file | Sort-Object Count -Descending | ForEach-Object {
        [pscustomobject]@{ file = $_.Name; hits = $_.Count }
    })
    $inventory = [ordered]@{
        schema = 1
        generated_at = (Get-Date -Format o)
        branch = $branch
        game_root = $game
        lua_root = $luaRoot
        lua_file_count = $luaFiles.Count
        match_count = $sorted.Count
        category_counts = $categoryCounts
        files_with_hits = $fileHitCounts
        safety = [ordered]@{
            scan_only = $true
            game_written = $false
            game_launched = $false
            save_or_progression_written = $false
        }
    }
    $inventory | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $inventoryPath -Encoding UTF8

    $precisionCandidates = @($luaFiles | Where-Object { $_.Name -ieq 'precisionchallenge.lua' })
    $precisionOut = New-Object System.Collections.Generic.List[string]
    foreach ($file in $precisionCandidates) {
        $precisionOut.Add("=== $($file.FullName) ===")
        $lines = [IO.File]::ReadAllLines($file.FullName)
        $interesting = New-Object 'System.Collections.Generic.HashSet[int]'
        for ($i = 0; $i -lt $lines.Length; $i++) {
            if ($lines[$i] -match '(?i)ravenKilled|checkpoint|restore|save|regionSummaryQuest|OnHitByWeapon|OnStart') {
                for ($j = [Math]::Max(0, $i - 3); $j -le [Math]::Min($lines.Length - 1, $i + 3); $j++) {
                    [void]$interesting.Add($j)
                }
            }
        }
        $last = -2
        foreach ($index in @($interesting | Sort-Object)) {
            if ($index -gt $last + 1) { $precisionOut.Add('---') }
            $precisionOut.Add(('{0,5}: {1}' -f ($index + 1), $lines[$index]))
            $last = $index
        }
    }
    if ($precisionCandidates.Count -eq 0) {
        $precisionOut.Add('No loose precisionchallenge.lua found under mods/lua.')
    }
    $precisionOut | Set-Content -LiteralPath $precisionPath -Encoding UTF8

    Write-Host "Matches: $($sorted.Count)"
    foreach ($key in $categoryCounts.Keys) {
        Write-Host ("  {0}: {1}" -f $key, $categoryCounts[$key])
    }
    Write-Host "Scan output: $relativeLogDir"
    Write-Host 'No game/save/progression write was performed.'

    Publish-Scan 'SCAN_PASSED'
    Write-Host 'SCAN_PASSED_AND_PUSHED'
}
catch {
    $message = $_.Exception.ToString()
    try { $message | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Scan 'SCAN_FAILED' } catch {
        Write-Host 'The scan failed and its log could not be published. Only in this case should console output be copied manually.' -ForegroundColor Red
    }
    exit 1
}
finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}
