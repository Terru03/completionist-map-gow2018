param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/source-scans/generic-collectible-state-api-usage-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$matchesPath = Join-Path $logDir 'matches.txt'
$summaryPath = Join-Path $logDir 'summary.json'
$published = $false
$transcriptStarted = $false

function Publish-Scan([string]$Result) {
    if ($script:published) { return }
    $script:published = $true
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }

    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
        'scan_only=true'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8

    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add of scan directory failed.' }
    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 0) { return }
    if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged scan changes.' }

    & git commit -m "Archive generic collectible state API usage scan $stamp" -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git commit of scan directory failed.' }
    & git push origin "HEAD:$expectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'git push of scan directory failed.' }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map generic collectible-state API usage scan ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"
    Write-Host 'Read-only scan of loose Lua sources. Game/save/progression are not written.'

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

    $luaRoot = Join-Path $game 'mods\lua'
    if (-not (Test-Path -LiteralPath $luaRoot -PathType Container)) {
        throw "Loose Lua root not found: $luaRoot"
    }

    $patterns = [ordered]@{
        counter_api = '(?i)\b(?:GetCounter|GetCounterChild|GetCounterChildrenCount|GetCounterCurrency|GetCounterCurrencyAdj|GetCounterMax|GetCounterMin|GetCounterName|GetCounterThreshold|GetCounterThresholdCount|GetCounterThresholdName|SetCounter|IncCounter)\s*\('
        ref_getter = '(?i)\b(?:GetRefBool|GetRefFloat|GetRefInt|GetRefString)\s*\('
        ref_setter = '(?i)\b(?:SetRefBool|SetRefFloat|SetRefInt|SetRefString)\s*\('
        resolve_object = '(?i)\bResolveGameObject\s*\('
        marker_id = '(?i)\bMarkerID\s*\('
        variable_api = '(?i)\b(?:GetVariable|SetVariable)\s*\('
        quest_state = '(?i)\b(?:GetQuestState|GetQuestStatus|CompleteQuest|ActivateQuest|IncrementQuest|IncrementQuestCounter|QuestManager\.[A-Za-z0-9_]+)\b'
        region_summary = '(?i)\bRegionSummary_[A-Za-z0-9_]+'
        checkpoint_fields = '(?i)\b(?:OnSaveCheckpoint|OnRestoreCheckpoint|SoftSave)\b'
        collectible_state_words = '(?i)\b(?:ravenKilled|opened|destroyed|collected|complete|completed|found|pickedUp|discovered|activated|broken|runeEnabled)\b'
    }

    $luaFiles = @(Get-ChildItem -LiteralPath $luaRoot -Recurse -File -Filter '*.lua' -ErrorAction Stop)
    $records = New-Object System.Collections.Generic.List[object]

    foreach ($file in $luaFiles) {
        $lines = [IO.File]::ReadAllLines($file.FullName)
        for ($i = 0; $i -lt $lines.Length; $i++) {
            $cats = New-Object System.Collections.Generic.List[string]
            foreach ($entry in $patterns.GetEnumerator()) {
                if ($lines[$i] -match $entry.Value) { $cats.Add([string]$entry.Key) }
            }
            if ($cats.Count -eq 0) { continue }

            $relative = $file.FullName.Substring($luaRoot.Length).TrimStart([char[]]@('\','/')).Replace('\','/')
            $start = [Math]::Max(0, $i - 5)
            $end = [Math]::Min($lines.Length - 1, $i + 5)
            $context = New-Object System.Collections.Generic.List[string]
            for ($j = $start; $j -le $end; $j++) {
                $prefix = if ($j -eq $i) { '>' } else { ' ' }
                $context.Add(('{0}{1,5}: {2}' -f $prefix, ($j + 1), $lines[$j]))
            }

            $records.Add([pscustomobject]@{
                file = $relative
                line = $i + 1
                categories = @($cats)
                text = $lines[$i].Trim()
                context = @($context)
            })
        }
    }

    $sorted = @($records | Sort-Object file, line)
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($record in $sorted) {
        $out.Add(('=== {0}:{1} [{2}] ===' -f $record.file, $record.line, ($record.categories -join ',')))
        foreach ($line in $record.context) { $out.Add($line) }
        $out.Add('')
    }
    if ($out.Count -eq 0) { $out.Add('No targeted API usages found.') }
    $out | Set-Content -LiteralPath $matchesPath -Encoding UTF8

    $categoryCounts = [ordered]@{}
    foreach ($key in $patterns.Keys) {
        $categoryCounts[$key] = @($sorted | Where-Object { $_.categories -contains $key }).Count
    }

    $apiHits = @($sorted | Where-Object {
        $_.categories -contains 'counter_api' -or
        $_.categories -contains 'ref_getter' -or
        $_.categories -contains 'ref_setter' -or
        $_.categories -contains 'resolve_object' -or
        $_.categories -contains 'marker_id' -or
        $_.categories -contains 'variable_api'
    } | ForEach-Object {
        [pscustomobject]@{
            file = $_.file
            line = $_.line
            categories = $_.categories
            text = $_.text
        }
    })

    $summary = [ordered]@{
        schema = 1
        generated_at = (Get-Date -Format o)
        branch = $branch
        lua_root = $luaRoot
        lua_file_count = $luaFiles.Count
        match_count = $sorted.Count
        category_counts = $categoryCounts
        candidate_native_api_hits = $apiHits
        safety = [ordered]@{
            scan_only = $true
            active_save_opened = $false
            game_written = $false
            save_or_progression_written = $false
            game_launched = $false
        }
    }
    $summary | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $summaryPath -Encoding UTF8

    Write-Host "Loose Lua files: $($luaFiles.Count)"
    Write-Host "Targeted matches: $($sorted.Count)"
    foreach ($key in $categoryCounts.Keys) {
        Write-Host ("  {0}: {1}" -f $key, $categoryCounts[$key])
    }
    Write-Host "candidate_native_api_hits=$($apiHits.Count)"
    Write-Host "Scan output: $relativeLogDir"
    Write-Host 'GENERIC_COLLECTIBLE_STATE_API_USAGE_SCAN_COMPLETED'

    Publish-Scan 'SCAN_PASSED'
    Write-Host 'SCAN_PASSED_AND_PUSHED'
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Scan 'SCAN_FAILED' } catch {
        Write-Host 'The scan failed and its log could not be published. Only then copy console output manually.' -ForegroundColor Red
    }
    exit 1
}
finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}
