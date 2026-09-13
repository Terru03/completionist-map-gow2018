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
$relativeLogDir = "archive/field-logs/source-scans/object-persistence-api-usage-$stamp"
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
    try {
        if ($script:transcriptStarted) {
            Stop-Transcript | Out-Null
            $script:transcriptStarted = $false
        }
        @(
            "result=$Result"
            "timestamp=$(Get-Date -Format o)"
            "branch=$expectedBranch"
            "active_save_opened=false"
            "game_written=false"
            "save_or_progression_written=false"
            "game_launched=false"
            "scan_only=true"
        ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8

        & git add -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git add of scan directory failed.' }
        & git diff --cached --quiet -- $relativeLogDir
        if ($LASTEXITCODE -eq 0) { return }
        & git commit -m "Archive object persistence API usage scan $stamp" -- $relativeLogDir
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

    Write-Host '=== Completionist Map object/persistence Lua API usage scan ==='
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

    $luaRoot = Join-Path $game 'mods\lua'
    if (-not (Test-Path -LiteralPath $luaRoot -PathType Container)) {
        throw "Loose Lua root not found: $luaRoot"
    }

    Write-Host 'Read-only scan: loose Lua source under mods\lua only.'
    Write-Host 'Active %USERPROFILE%\Saved Games\God of War is explicitly not opened.'
    Write-Host 'The game is not launched.'

    $patterns = [ordered]@{
        load_subobject = '(?i)\bLoadSubObject\b'
        subobject_api = '(?i)\bgame\.SubObject\.[A-Za-z0-9_]+'
        subobject_env = '(?i)\b(?:DebugGetSubObjectEnvironmentRoot|CurrentlyExecutingSubObject)\b'
        object_lookup = '(?i)(?:[:\.]|\b)(?:FindSingleGameObject|FindGameObjects|FindGameObject|GetGameObject|IterateGameObjects)\s*\('
        wad_api = '(?i)\b(?:GetAvailableWads|GetPermWad|GetUIWad|[A-Za-z0-9_]*(?:Load|Unload|Stream|Preload)[A-Za-z0-9_]*Wad[A-Za-z0-9_]*|[A-Za-z0-9_]*Wad[A-Za-z0-9_]*(?:Load|Unload|Stream|Preload)[A-Za-z0-9_]*)\b'
        world_lookup = '(?i)\b(?:FindAnything|ExcludeGameObject)\s*\('
        gameobjects_registry = '(?i)\bGameObjects\s*\['
        checkpoint_retention = '(?i)\b(?:SetRetainOnCheckpoint|SetForgetOnCheckpoint|SoftSave)\b'
        guid_identity = '(?i)\b(?:GUID|Guid|guid|InstanceGuid|InstanceGUID|GetID|UniqueName)\b'
        exact_target = '(?i)642d0d16[-]?4af0[-]?a5d4[-]?076e[-]?77933c549a5d|xpl200_funeral|RegionSummary_VF_Raven_Parent'
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

            $relative = [IO.Path]::GetRelativePath($luaRoot, $file.FullName).Replace('\','/')
            $start = [Math]::Max(0, $i - 3)
            $end = [Math]::Min($lines.Length - 1, $i + 3)
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

    $filesWithHits = @($sorted | Group-Object file | Sort-Object Count -Descending | ForEach-Object {
        [pscustomobject]@{ file = $_.Name; hits = $_.Count }
    })

    $summary = [ordered]@{
        schema = 1
        generated_at = (Get-Date -Format o)
        branch = $branch
        lua_root = $luaRoot
        lua_file_count = $luaFiles.Count
        match_count = $sorted.Count
        category_counts = $categoryCounts
        files_with_hits = $filesWithHits
        exact_target_hits = @($sorted | Where-Object { $_.categories -contains 'exact_target' } | ForEach-Object {
            [pscustomobject]@{ file = $_.file; line = $_.line; text = $_.text }
        })
        safety = [ordered]@{
            scan_only = $true
            active_save_opened = $false
            game_written = $false
            save_or_progression_written = $false
            game_launched = $false
        }
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding UTF8

    Write-Host "Loose Lua files: $($luaFiles.Count)"
    Write-Host "Targeted matches: $($sorted.Count)"
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
        Write-Host 'The scan failed and its log could not be published. Only then copy console output manually.' -ForegroundColor Red
    }
    exit 1
}
finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}
