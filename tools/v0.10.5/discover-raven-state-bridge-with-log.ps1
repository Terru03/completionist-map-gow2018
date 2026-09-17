param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$expectedBranch = 'codex/all-collectibles-production-research'
$stateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-runtime-test\transaction'
$activeManifest = Join-Path $stateRoot 'active.json'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$archive = Join-Path $repo "archive\field-logs\source-scans\raven-state-bridge-static-$timestamp"
$reportPath = Join-Path $archive 'report.txt'
$jsonPath = Join-Path $archive 'report.json'
$resultPath = Join-Path $archive 'result.txt'
$errorPath = Join-Path $archive 'error.txt'
New-Item -ItemType Directory -Force -Path $archive | Out-Null

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-Entry([object]$Manifest, [string]$Relative) {
    $needle = $Relative.Replace('\','/').ToLowerInvariant()
    foreach ($entry in @($Manifest.entries)) {
        if (([string]$entry.relative).Replace('\','/').ToLowerInvariant() -eq $needle) { return $entry }
    }
    throw "Active transaction does not contain $Relative"
}

function Get-BackupPath([object]$Manifest, [object]$Entry) {
    if (-not [bool]$Entry.existed_before) { throw "No pristine backup exists for $($Entry.relative)" }
    $relative = [string]$Entry.backup_relative
    if ([string]::IsNullOrWhiteSpace($relative)) { throw "Missing backup_relative for $($Entry.relative)" }
    $root = [IO.Path]::GetFullPath([string]$Manifest.transaction_root)
    $path = [IO.Path]::GetFullPath((Join-Path $root $relative))
    $prefix = $root.TrimEnd('\') + '\'
    if (-not $path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Backup path escaped transaction root.' }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Backup file missing: $path" }
    if ((Get-Sha256 $path) -ne ([string]$Entry.before_sha256).ToLowerInvariant()) { throw "Backup SHA mismatch: $($Entry.relative)" }
    return $path
}

function Add-ContextMatches([System.Collections.Generic.List[string]]$Lines, [string]$Label, [string]$Path, [string[]]$Patterns, [int]$Context = 12) {
    $Lines.Add('')
    $Lines.Add("=== $Label ===")
    $Lines.Add("path=$Path")
    $content = @(Get-Content -LiteralPath $Path)
    $hits = New-Object System.Collections.Generic.SortedSet[int]
    for ($i = 0; $i -lt $content.Count; $i++) {
        foreach ($pattern in $Patterns) {
            if ($content[$i] -match $pattern) { [void]$hits.Add($i); break }
        }
    }
    $Lines.Add("match_lines=$($hits.Count)")
    $emitted = New-Object System.Collections.Generic.HashSet[int]
    foreach ($hit in $hits) {
        $start = [Math]::Max(0, $hit - $Context)
        $end = [Math]::Min($content.Count - 1, $hit + $Context)
        $Lines.Add("--- context around line $($hit + 1) ---")
        for ($j = $start; $j -le $end; $j++) {
            if ($emitted.Add($j)) { $Lines.Add(('{0,6}: {1}' -f ($j + 1), $content[$j])) }
        }
    }
}

function Collect-ApiSymbols([string]$LuaRoot) {
    $symbols = @{}
    $interesting = New-Object System.Collections.Generic.List[object]
    if (-not (Test-Path -LiteralPath $LuaRoot -PathType Container)) {
        return [pscustomobject]@{ Symbols = $symbols; Interesting = @(); FilesScanned = 0 }
    }
    $files = @(Get-ChildItem -LiteralPath $LuaRoot -Recurse -File -Filter '*.lua')
    $rx = [regex]'(?<![A-Za-z0-9_])((?:game\.)?(?:Map|Compass|Progression|Save|Checkpoint|Quest|GameObject|World|Entity|Level|Global)[\.:][A-Za-z_][A-Za-z0-9_]*)'
    $focus = [regex]'(?i)(ravenKilled|RegionSummary_.*_Raven_Parent|serialize|deserialize|pickle|unpickle|checkpoint|progression|save|restore|gameobject)'
    foreach ($file in $files) {
        $lineNo = 0
        foreach ($line in Get-Content -LiteralPath $file.FullName) {
            $lineNo++
            foreach ($m in $rx.Matches($line)) {
                $key = $m.Groups[1].Value
                if (-not $symbols.ContainsKey($key)) { $symbols[$key] = 0 }
                $symbols[$key]++
            }
            if ($focus.IsMatch($line)) {
                $interesting.Add([pscustomobject]@{
                    file = $file.FullName.Substring($LuaRoot.Length).TrimStart('\')
                    line = $lineNo
                    text = $line.Trim()
                })
            }
        }
    }
    return [pscustomobject]@{ Symbols = $symbols; Interesting = @($interesting); FilesScanned = $files.Count }
}

try {
    $branch = (& git -C $repo branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne $expectedBranch) { throw "Expected branch '$expectedBranch', got '$branch'." }
    if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }
    if (-not (Test-Path -LiteralPath (Join-Path $GameRoot 'GoW.exe') -PathType Leaf)) { throw 'GoW.exe missing from GameRoot.' }
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) { throw "Missing active all-Ravens transaction manifest: $activeManifest" }

    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    if ([string]$manifest.status -ne 'installed') { throw "Expected installed active transaction, got '$($manifest.status)'." }
    if (@($manifest.entries).Count -ne 5) { throw 'Expected exactly five active all-Ravens transaction entries.' }

    $eventRelative = 'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua'
    $mapRelative = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
    $eventEntry = Get-Entry $manifest $eventRelative
    $mapEntry = Get-Entry $manifest $mapRelative
    $stockEvent = Get-BackupPath $manifest $eventEntry
    $stockMap = Get-BackupPath $manifest $mapEntry

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add('Completionist Map - Raven state bridge static discovery')
    $lines.Add("timestamp=$((Get-Date).ToString('o'))")
    $lines.Add("branch=$branch")
    $lines.Add("active_transaction=$($manifest.transaction_id)")
    $lines.Add("active_status=$($manifest.status)")
    $lines.Add("stock_precisionchallenge_sha256=$(Get-Sha256 $stockEvent)")
    $lines.Add("stock_mapmenu_sha256=$(Get-Sha256 $stockMap)")
    $lines.Add('game_files_written=false')
    $lines.Add('save_or_progression_written=false')
    $lines.Add('game_launched=false')

    Add-ContextMatches $lines 'PRISTINE PRECISIONCHALLENGE RAVEN/PERSISTENCE CONTEXT' $stockEvent @(
        'ravenKilled', 'OnSave', 'OnLoad', 'OnRestore', 'Checkpoint', 'Serialize', 'Deserialize', 'Pickle', 'Unpickle', 'regionSummaryQuest'
    ) 18
    Add-ContextMatches $lines 'PRISTINE MAPMENU STATE/API CONTEXT' $stockMap @(
        'game\.Map', 'Map\.', 'game\.Compass', 'Progression', 'Checkpoint', 'Save', 'Restore'
    ) 5

    $luaRoot = Join-Path $GameRoot 'mods\lua'
    $inventory = Collect-ApiSymbols $luaRoot
    $lines.Add('')
    $lines.Add('=== SHIPPED LUA ENGINE API SYMBOL INVENTORY ===')
    $lines.Add("lua_files_scanned=$($inventory.FilesScanned)")
    foreach ($key in @($inventory.Symbols.Keys | Sort-Object)) {
        $lines.Add("$key`t$($inventory.Symbols[$key])")
    }
    $lines.Add('')
    $lines.Add('=== SHIPPED LUA PERSISTENCE/GAMEOBJECT LINES ===')
    foreach ($row in @($inventory.Interesting | Select-Object -First 2500)) {
        $lines.Add("$($row.file):$($row.line): $($row.text)")
    }

    [IO.File]::WriteAllLines($reportPath, $lines, (New-Object System.Text.UTF8Encoding($false)))

    $json = [ordered]@{
        schema = 1
        result = 'RAVEN_STATE_BRIDGE_STATIC_DISCOVERY_PASSED'
        timestamp = (Get-Date).ToString('o')
        branch = $branch
        active_transaction = [string]$manifest.transaction_id
        active_status = [string]$manifest.status
        pristine = [ordered]@{
            precisionchallenge_sha256 = Get-Sha256 $stockEvent
            mapmenu_sha256 = Get-Sha256 $stockMap
        }
        lua_files_scanned = [int]$inventory.FilesScanned
        api_symbols = [ordered]@{}
        safety = [ordered]@{
            game_files_written = $false
            save_or_progression_written = $false
            game_launched = $false
            active_transaction_modified = $false
        }
    }
    foreach ($key in @($inventory.Symbols.Keys | Sort-Object)) { $json.api_symbols[$key] = [int]$inventory.Symbols[$key] }
    $json | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $jsonPath -Encoding UTF8
    @(
        'result=RAVEN_STATE_BRIDGE_STATIC_DISCOVERY_PASSED',
        "timestamp=$((Get-Date).ToString('o'))",
        "active_transaction=$($manifest.transaction_id)",
        'game_files_written=false',
        'save_or_progression_written=false',
        'game_launched=false'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8

    Push-Location $repo
    try {
        git add -- $archive
        git commit -m "research: capture Raven state bridge static evidence $timestamp"
        if ($LASTEXITCODE -ne 0) { throw "git commit failed with exit code $LASTEXITCODE" }
        git push origin $expectedBranch
        if ($LASTEXITCODE -ne 0) { throw "git push failed with exit code $LASTEXITCODE" }
    }
    finally { Pop-Location }

    Write-Host 'DONE'
}
catch {
    $_ | Out-String | Set-Content -LiteralPath $errorPath -Encoding UTF8
    @(
        'result=RAVEN_STATE_BRIDGE_STATIC_DISCOVERY_FAILED',
        "timestamp=$((Get-Date).ToString('o'))",
        'game_files_written=false',
        'save_or_progression_written=false',
        'game_launched=false'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
    try {
        Push-Location $repo
        git add -- $archive
        git commit -m "research: capture failed Raven state bridge static evidence $timestamp" | Out-Host
        if ($LASTEXITCODE -eq 0) { git push origin $expectedBranch | Out-Host }
    }
    catch {}
    finally { try { Pop-Location } catch {} }
    throw
}
