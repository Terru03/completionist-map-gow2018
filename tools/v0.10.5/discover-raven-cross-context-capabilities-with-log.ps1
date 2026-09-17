param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$expectedBranch = 'codex/all-collectibles-production-research'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$archive = Join-Path $repo "archive\field-logs\source-scans\raven-cross-context-capabilities-$timestamp"
$reportPath = Join-Path $archive 'report.txt'
$resultPath = Join-Path $archive 'result.txt'
$errorPath = Join-Path $archive 'error.txt'
New-Item -ItemType Directory -Force -Path $archive | Out-Null

function Add-Count([hashtable]$Table, [string]$Key) {
    if (-not $Table.ContainsKey($Key)) { $Table[$Key] = 0 }
    $Table[$Key] = [int]$Table[$Key] + 1
}

function Commit-Archive([string]$Message) {
    Push-Location $repo
    try {
        git add -- $archive
        if ($LASTEXITCODE -ne 0) { throw 'git add failed' }
        git commit -m $Message
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed' }
        git push origin $expectedBranch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed' }
    }
    finally { Pop-Location }
}

try {
    $branch = (& git -C $repo branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne $expectedBranch) { throw "Expected branch '$expectedBranch', got '$branch'." }
    $luaRoot = Join-Path $GameRoot 'mods\lua'
    if (-not (Test-Path -LiteralPath $luaRoot -PathType Container)) { throw "Lua root missing: $luaRoot" }

    $files = @(Get-ChildItem -LiteralPath $luaRoot -Recurse -File -Filter '*.lua')
    $symbolCounts = @{}
    $channelCounts = @{}
    $hitLines = New-Object System.Collections.ArrayList

    $gameRx = [regex]'(?<![A-Za-z0-9_])(game\.[A-Za-z_][A-Za-z0-9_]*(?:[\.:][A-Za-z_][A-Za-z0-9_]*)+)'
    $channelRx = [regex]'(?<![A-Za-z0-9_])(io\.[A-Za-z_][A-Za-z0-9_]*|os\.[A-Za-z_][A-Za-z0-9_]*|package\.[A-Za-z_][A-Za-z0-9_]*|debug\.[A-Za-z_][A-Za-z0-9_]*|dofile|loadfile|loadstring|require|setfenv|getfenv)'
    $managerRx = [regex]'(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*(?:Manager|System|Store|Registry|Session|Profile|Checkpoint|SaveState|GameState|Persistence|Progression|Quest)[\.:][A-Za-z_][A-Za-z0-9_]*)'
    $focusRx = [regex]'(?i)(checkpoint|restore|save|persist|pickle|userdata|gameobject|global|session|profile|ravenKilled|shared|registry|quest|progression)'

    foreach ($file in $files) {
        $lineNo = 0
        foreach ($line in Get-Content -LiteralPath $file.FullName) {
            $lineNo++
            foreach ($m in $gameRx.Matches($line)) { Add-Count $symbolCounts $m.Groups[1].Value }
            foreach ($m in $managerRx.Matches($line)) { Add-Count $symbolCounts $m.Groups[1].Value }
            foreach ($m in $channelRx.Matches($line)) { Add-Count $channelCounts $m.Groups[1].Value }
            if ($channelRx.IsMatch($line) -or $focusRx.IsMatch($line)) {
                if ($hitLines.Count -lt 10000) {
                    $relative = $file.FullName.Substring($luaRoot.Length).TrimStart('\')
                    [void]$hitLines.Add("$relative`:$lineNo`: $($line.Trim())")
                }
            }
        }
    }

    $out = New-Object System.Collections.Generic.List[string]
    $out.Add('Completionist Map - broad Raven cross-context capability scan')
    $out.Add("timestamp=$((Get-Date).ToString('o'))")
    $out.Add("branch=$branch")
    $out.Add("lua_files_scanned=$($files.Count)")
    $out.Add('game_files_written=false')
    $out.Add('save_or_progression_written=false')
    $out.Add('game_launched=false')
    $out.Add('')
    $out.Add('=== STANDARD LUA CROSS-CONTEXT CHANNELS ===')
    foreach ($key in @($channelCounts.Keys | Sort-Object)) { $out.Add("$key`t$($channelCounts[$key])") }
    $out.Add('')
    $out.Add('=== BROAD ENGINE/MANAGER SYMBOLS ===')
    foreach ($key in @($symbolCounts.Keys | Sort-Object)) { $out.Add("$key`t$($symbolCounts[$key])") }
    $out.Add('')
    $out.Add('=== PERSISTENCE/CROSS-CONTEXT SOURCE LINES ===')
    foreach ($line in $hitLines) { $out.Add([string]$line) }
    [IO.File]::WriteAllLines($reportPath, $out, (New-Object System.Text.UTF8Encoding($false)))

    @(
        'result=RAVEN_CROSS_CONTEXT_CAPABILITY_SCAN_PASSED',
        "timestamp=$((Get-Date).ToString('o'))",
        "lua_files_scanned=$($files.Count)",
        "standard_channel_symbol_count=$($channelCounts.Count)",
        "engine_symbol_count=$($symbolCounts.Count)",
        'game_files_written=false',
        'save_or_progression_written=false',
        'game_launched=false'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8

    Commit-Archive "research: capture Raven cross-context capabilities $timestamp"
    Write-Host 'DONE'
}
catch {
    $_ | Out-String | Set-Content -LiteralPath $errorPath -Encoding UTF8
    @(
        'result=RAVEN_CROSS_CONTEXT_CAPABILITY_SCAN_FAILED',
        "timestamp=$((Get-Date).ToString('o'))",
        'game_files_written=false',
        'save_or_progression_written=false',
        'game_launched=false'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
    try { Commit-Archive "research: capture failed Raven cross-context capabilities $timestamp" } catch {}
    throw
}
