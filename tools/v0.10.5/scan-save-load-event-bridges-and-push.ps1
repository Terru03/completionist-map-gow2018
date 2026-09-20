param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $RepoRoot

$branch = (& git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) { throw "Wrong branch '$branch'; expected '$ExpectedBranch'." }

$staged = @(& git diff --cached --name-only)
if ($staged.Count -gt 0) { throw "Refusing pre-existing staged changes: $($staged -join ', ')" }

$roots = @(
    (Join-Path $GameRoot 'mods\lua_source'),
    (Join-Path $GameRoot 'mods\lua')
) | Where-Object { Test-Path -LiteralPath $_ -PathType Container }

if ($roots.Count -eq 0) { throw "No Lua source roots found under $GameRoot\mods." }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeDir = "archive/field-logs/source-scans/save-load-event-bridges-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$report = Join-Path $outDir 'report.txt'
$jsonPath = Join-Path $outDir 'report.json'

$terms = @(
    'EVT_LoadSaveData',
    'EVT_LoadSaveFile_Done',
    'EVT_ManualSaveComplete',
    'EVT_AutoSave',
    'GetAvailableBookmarks',
    'StoreCheckpoint',
    'StoreCheckpointAndBookmark',
    'RestartFromCheckpoint',
    '__hook_thunks',
    'thunk.Install',
    'EngineEvents',
    'ManualSaveComplete',
    'LoadSaveData',
    'LoadSaveFile_Done'
)

$transcript = $false
$published = $false

function Publish-Scan([string]$result) {
    if ($script:published) { return }
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
    @(
        "result=$result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$ExpectedBranch"
        'scan_only=true'
        'game_launched=false'
        'active_save_opened=false'
        'save_written=false'
        'progression_written=false'
        'game_files_written=false'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relativeDir
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "research(v0.10.5): scan save-load event bridges $stamp" -- $relativeDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin $ExpectedBranch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff --cached failed.'
    }
    $script:published = $true
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true

    $files = @()
    foreach ($root in $roots) {
        $files += @(Get-ChildItem -LiteralPath $root -Recurse -File -Filter '*.lua' -ErrorAction Stop)
    }
    $files = @($files | Sort-Object FullName -Unique)

    $hits = New-Object System.Collections.Generic.List[object]
    foreach ($file in $files) {
        $lines = [IO.File]::ReadAllLines($file.FullName)
        for ($i = 0; $i -lt $lines.Length; $i++) {
            $matched = @($terms | Where-Object { $lines[$i].IndexOf($_, [StringComparison]::OrdinalIgnoreCase) -ge 0 })
            if ($matched.Count -eq 0) { continue }

            $start = [Math]::Max(0, $i - 10)
            $end = [Math]::Min($lines.Length - 1, $i + 14)
            $context = New-Object System.Collections.Generic.List[string]
            for ($j = $start; $j -le $end; $j++) {
                $mark = if ($j -eq $i) { '>>' } else { '  ' }
                $context.Add(('{0} {1,5}: {2}' -f $mark, ($j + 1), $lines[$j]))
            }

            $rootMatch = $roots | Where-Object { $file.FullName.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
            $relative = if ($rootMatch) { [IO.Path]::GetRelativePath($rootMatch, $file.FullName) } else { $file.FullName }

            $hits.Add([pscustomobject]@{
                file = $relative.Replace('\','/')
                full_path = $file.FullName
                line = $i + 1
                terms = @($matched)
                text = $lines[$i].Trim()
                context = @($context)
            })
        }
    }

    $ordered = @($hits | Sort-Object file, line)
    $out = New-Object System.Collections.Generic.List[string]
    $out.Add('Completionist Map - save/load event bridge source scan')
    $out.Add("lua_files_scanned=$($files.Count)")
    $out.Add("hit_count=$($ordered.Count)")
    $out.Add('game_launched=false active_save_opened=false save_written=false progression_written=false')
    $out.Add('')
    foreach ($hit in $ordered) {
        $out.Add(('FILE {0} line={1} terms={2}' -f $hit.file, $hit.line, ($hit.terms -join ',')))
        foreach ($line in $hit.context) { $out.Add($line) }
        $out.Add('')
    }
    $out | Set-Content -LiteralPath $report -Encoding UTF8

    $summary = [ordered]@{}
    foreach ($term in $terms) {
        $summary[$term] = @($ordered | Where-Object { $_.terms -contains $term }).Count
    }

    [ordered]@{
        schema = 1
        analysis = 'save_load_event_bridge_source_scan'
        roots = @($roots)
        lua_files_scanned = $files.Count
        hit_count = $ordered.Count
        term_counts = $summary
        hits = $ordered
        safety = [ordered]@{
            scan_only = $true
            game_launched = $false
            active_save_opened = $false
            save_written = $false
            progression_written = $false
            game_files_written = $false
        }
    } | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

    Write-Host "SAVE_LOAD_EVENT_BRIDGE_SCAN_COMPLETE files=$($files.Count) hits=$($ordered.Count)"
    foreach ($term in $terms) {
        Write-Host ("  {0}={1}" -f $term, $summary[$term])
    }

    Publish-Scan 'SAVE_LOAD_EVENT_BRIDGE_SCAN_PASSED'
    $head = (& git rev-parse HEAD).Trim()
    Write-Host "SAVE_LOAD_EVENT_BRIDGE_SCAN_PUSHED $head" -ForegroundColor Green
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SAVE_LOAD_EVENT_BRIDGE_SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Scan 'SAVE_LOAD_EVENT_BRIDGE_SCAN_FAILED' } catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 1
}
finally {
    if ($transcript) { try { Stop-Transcript | Out-Null } catch {} }
}
