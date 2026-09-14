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
$relativeLogDir = "archive/field-logs/source-scans/core-save-restore-dispatch-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$resultPath = Join-Path $logDir 'result.txt'
$coreSaveOut = Join-Path $logDir 'core-save.lua.txt'
$usageOut = Join-Path $logDir 'load-callback-usages.txt'
$transcriptStarted = $false
$published = $false

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Publish-Scan([string]$result) {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    @(
        "result=$result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        'game_launched=false'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'scan_only=true'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8

    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    $prefix = ($relativeLogDir -replace '\\','/').TrimEnd('/') + '/'
    $foreign = @($staged | Where-Object { -not (($_ -replace '\\','/').StartsWith($prefix)) })
    if ($foreign.Count -gt 0) {
        & git restore --staged -- $relativeLogDir 2>$null
        throw "Refusing to commit unrelated staged paths: $($foreign -join ', ')"
    }

    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 0) { return }
    if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged scan.' }

    & git commit -m "Archive core save restore dispatch scan $stamp" -- $relativeLogDir | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    & git push origin "HEAD:$expectedBranch" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map core.save restore dispatch scan ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"
    Write-Host 'Read-only loose-Lua source scan. God of War is not launched.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch. Expected '$expectedBranch', found '$branch'." }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing to run with staged changes: $($staged -join ', ')" }

    $roots = @(
        (Join-Path $GameRoot 'mods\lua_source'),
        (Join-Path $GameRoot 'mods\lua')
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Container }
    if ($roots.Count -eq 0) { throw 'No loose Lua source roots found.' }

    $allLua = @()
    foreach ($root in $roots) {
        $allLua += @(Get-ChildItem -LiteralPath $root -Recurse -File -Filter '*.lua' -ErrorAction SilentlyContinue)
    }
    if ($allLua.Count -eq 0) { throw 'No Lua files found.' }

    $coreCandidates = @($allLua | Where-Object {
        $norm = $_.FullName.Replace('/','\').ToLowerInvariant()
        $norm.EndsWith('\gameart\scripts\libraries\core\save.lua') -or $norm.EndsWith('\core\save.lua')
    })
    if ($coreCandidates.Count -eq 0) { throw 'core.save.lua was not found.' }

    # Prefer lua_source when both source and live copies exist.
    $core = $coreCandidates | Sort-Object @{Expression={ if ($_.FullName -match '\\lua_source\\') { 0 } else { 1 } }}, FullName | Select-Object -First 1
    Write-Host "core.save source: $($core.FullName)"

    $coreLines = @(Get-Content -LiteralPath $core.FullName)
    $numbered = for ($i = 0; $i -lt $coreLines.Count; $i++) {
        '{0,4}: {1}' -f ($i + 1), $coreLines[$i]
    }
    @(
        'Completionist Map - core.save full source'
        "timestamp=$stamp"
        "source=$($core.FullName)"
        "line_count=$($coreLines.Count)"
        ''
        $numbered
    ) | Set-Content -LiteralPath $coreSaveOut -Encoding UTF8

    $terms = @(
        'AddLoadObjectCallback',
        'AddLoadSystemCallback',
        'AddSaveObjectCallback',
        'AddSaveSystemCallback',
        'GetSaveState',
        'CreateSaveState',
        'object_savestate',
        'load_object',
        'load_system',
        'OnRestoreCheckpoint',
        'RestoreCheckpoint'
    )

    $contexts = New-Object System.Collections.Generic.List[string]
    $matchCount = 0
    foreach ($file in $allLua) {
        $lines = @(Get-Content -LiteralPath $file.FullName -ErrorAction SilentlyContinue)
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $hitTerms = @($terms | Where-Object { $lines[$i].IndexOf($_, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 })
            if ($hitTerms.Count -eq 0) { continue }
            $matchCount++
            $start = [Math]::Max(0, $i - 8)
            $end = [Math]::Min($lines.Count - 1, $i + 12)
            $contexts.Add(('=' * 100))
            $contexts.Add("FILE $($file.FullName)")
            $contexts.Add("MATCH line=$($i + 1) terms=$($hitTerms -join ',')")
            for ($j = $start; $j -le $end; $j++) {
                $marker = if ($j -eq $i) { '>>' } else { '  ' }
                $contexts.Add(('{0} {1,5}: {2}' -f $marker, ($j + 1), $lines[$j]))
            }
            $contexts.Add('')
        }
    }

    @(
        'Completionist Map - core.save/load callback usage contexts'
        "timestamp=$stamp"
        "lua_files_scanned=$($allLua.Count)"
        "matches=$matchCount"
        ''
        $contexts
    ) | Set-Content -LiteralPath $usageOut -Encoding UTF8

    Write-Host "Lua files scanned: $($allLua.Count)"
    Write-Host "core.save lines: $($coreLines.Count)"
    Write-Host "Relevant source matches: $matchCount"
    Write-Host 'CORE_SAVE_RESTORE_DISPATCH_SCAN_PASSED'
    Publish-Scan 'CORE_SAVE_RESTORE_DISPATCH_SCANNED'
    Write-Host 'SCAN_PASSED_AND_PUSHED'
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Scan 'CORE_SAVE_RESTORE_DISPATCH_SCAN_FAILED' } catch { Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    Stop-LocalTranscript
}
