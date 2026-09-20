param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $RepoRoot

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeDir = "archive/field-logs/runtime-captures/current-save-slot-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$console = Join-Path $outDir 'console-log.txt'
$extract = Join-Path $outDir 'probe-extract.txt'
$target = Join-Path $GameRoot 'mods\lua\gameart\scripts\libraries\ui\fsm.lua'
$sourceFallback = Join-Path $GameRoot 'mods\lua_source\gameart\scripts\libraries\ui\fsm.lua'
$helper = Join-Path $RepoRoot 'tools\v0.10.5\current-save-slot-probe.lua'
$targetExisted = Test-Path -LiteralPath $target -PathType Leaf
$loaderLog = Join-Path $GameRoot 'mods\loader_log.txt'
$exe = Join-Path $GameRoot 'GoW.exe'
$backup = Join-Path $env:TEMP "completionist-current-slot-$stamp.bak"

$restored = $false
$published = $false
$transcript = $false
$launched = $false

function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
}

function Restore-Target {
    if ($script:restored) { return }
    if ($script:targetExisted) {
        if (Test-Path -LiteralPath $backup -PathType Leaf) {
            [IO.File]::WriteAllBytes($target, [IO.File]::ReadAllBytes($backup))
            $script:restored = $true
        }
    } else {
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            Remove-Item -LiteralPath $target -Force
        }
        $script:restored = $true
    }
}

function Publish-Capture([string]$result) {
    if ($script:published) { return }
    Stop-LocalTranscript
    @(
        "result=$result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$ExpectedBranch"
        "game_launched=$($script:launched.ToString().ToLowerInvariant())"
        "target_restored=$($script:restored.ToString().ToLowerInvariant())"
        'probe_read_only=true'
        'save_written_by_probe=false'
        'progression_written_by_probe=false'
        'normal_game_save_activity_not_blocked=true'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relativeDir
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "research(v0.10.5): capture current save slot $stamp" -- $relativeDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin $ExpectedBranch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff --cached failed.'
    }
    $script:published = $true
}

try {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $ExpectedBranch) { throw "Wrong branch '$branch'; expected '$ExpectedBranch'." }
    $staged = @(& git diff --cached --name-only)
    if ($staged.Count -gt 0) { throw "Refusing pre-existing staged changes: $($staged -join ', ')" }
    foreach ($path in @($helper, $exe)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required file: $path" }
    }
    if (-not $targetExisted -and -not (Test-Path -LiteralPath $sourceFallback -PathType Leaf)) {
        throw "Missing both runtime override and vanilla source for fsm.lua: $target ; $sourceFallback"
    }
    if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
        throw 'Close God of War before running this capture.'
    }

    $sourcePath = if ($targetExisted) { $target } else { $sourceFallback }
    $original = [IO.File]::ReadAllBytes($sourcePath)
    if ($targetExisted) {
        [IO.File]::WriteAllBytes($backup, $original)
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    }
    $beforeHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $sourceText = [IO.File]::ReadAllText($sourcePath, [Text.Encoding]::UTF8).Replace("`r`n", "`n").Replace("`r", "`n")
    $helperText = [IO.File]::ReadAllText($helper, [Text.Encoding]::UTF8).Replace("`r`n", "`n").Replace("`r", "`n")
    $combinedText = $helperText + "`n" + $sourceText
    [IO.File]::WriteAllText($target, $combinedText, (New-Object Text.UTF8Encoding($false)))

    $installedHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    @(
        "fsm_before_sha256=$beforeHash"
        "fsm_probe_installed_sha256=$installedHash"
        "helper_sha256=$((Get-FileHash -LiteralPath $helper -Algorithm SHA256).Hash.ToLowerInvariant())"
        "target=$target"
        "source_path=$sourcePath"
        "target_existed_before=$($targetExisted.ToString().ToLowerInvariant())"
        "temporary_override=$(((-not $targetExisted)).ToString().ToLowerInvariant())"
        "probe_prepend=true"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'installed-file-hashes.txt') -Encoding UTF8

    $beforeLines = @()
    if (Test-Path -LiteralPath $loaderLog -PathType Leaf) {
        $beforeLines = @(Get-Content -LiteralPath $loaderLog)
    }

    Write-Host 'CURRENT SAVE SLOT PERSISTENCE CAPTURE - READ ONLY' -ForegroundColor Cyan
    Write-Host 'God of War will launch now.'
    Write-Host 'From the main menu, load your almost-done save normally.'
    Write-Host 'Once gameplay is fully loaded, wait a few seconds, then quit God of War fully.'
    Write-Host 'Do not kill or collect anything during this capture.'
    Start-Process -FilePath $exe -WorkingDirectory $GameRoot | Out-Null
    $launched = $true

    while ($true) {
        Read-Host 'After God of War has fully exited, press Enter' | Out-Null
        if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -eq 0) { break }
        Write-Host 'God of War is still running. Quit it fully first.' -ForegroundColor Yellow
    }

    $fresh = @()
    if (Test-Path -LiteralPath $loaderLog -PathType Leaf) {
        Copy-Item -LiteralPath $loaderLog -Destination (Join-Path $outDir 'loader_log.txt') -Force
        $afterLines = @(Get-Content -LiteralPath $loaderLog)
        $prefixMatches = $beforeLines.Count -le $afterLines.Count
        if ($prefixMatches) {
            for ($i = 0; $i -lt $beforeLines.Count; $i++) {
                if ($beforeLines[$i] -cne $afterLines[$i]) { $prefixMatches = $false; break }
            }
        }
        if ($prefixMatches) {
            $fresh = @($afterLines | Select-Object -Skip $beforeLines.Count)
        } else {
            $fresh = $afterLines
        }
    }

    $probeLines = @($fresh | Select-String -SimpleMatch '[CompletionistCurrentSlotProbe]' | ForEach-Object { $_.Line })
    if ($probeLines.Count -gt 0) {
        $probeLines | Set-Content -LiteralPath $extract -Encoding UTF8
    } else {
        'NO_COMPLETIONIST_CURRENT_SLOT_PROBE_LINES_FOUND' | Set-Content -LiteralPath $extract -Encoding UTF8
    }

    Restore-Target
    if ($targetExisted) {
        $afterHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
        $exactRestore = $afterHash -eq $beforeHash
    } else {
        $afterHash = '<absent>'
        $exactRestore = -not (Test-Path -LiteralPath $target -PathType Leaf)
    }
    @(
        "fsm_before_sha256=$beforeHash"
        "fsm_after_restore_sha256=$afterHash"
        "target_existed_before=$($targetExisted.ToString().ToLowerInvariant())"
        "exact_restore=$($exactRestore.ToString().ToLowerInvariant())"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'restore-verification.txt') -Encoding UTF8
    if (-not $exactRestore) { throw 'fsm.lua restore/remove verification failed.' }

    $successful = @($probeLines | Select-String -SimpleMatch ' getOk=true ' | ForEach-Object { $_.Line })
    $slotValues = @()
    foreach ($line in $successful) {
        if ($line -match ' slot=([^ ]+)') { $slotValues += $Matches[1] }
    }
    @(
        "probe_line_count=$($probeLines.Count)"
        "successful_get_count=$($successful.Count)"
        "slot_values=$($slotValues -join ',')"
        "non_nil_slot_count=$(@($slotValues | Where-Object { $_ -ne 'nil' }).Count)"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'slot-summary.txt') -Encoding UTF8

    $result = if ($successful.Count -gt 0) { 'CURRENT_SAVE_SLOT_CAPTURED' } else { 'CURRENT_SAVE_SLOT_NOT_CAPTURED' }
    Publish-Capture $result
    $head = (& git rev-parse HEAD).Trim()
    Write-Host "CURRENT_SAVE_SLOT_CAPTURE_PUSHED $head" -ForegroundColor Green
    Write-Host "Evidence: $relativeDir"
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "CURRENT_SAVE_SLOT_CAPTURE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Restore-Target } catch {}
    try { Publish-Capture 'CURRENT_SAVE_SLOT_CAPTURE_FAILED' } catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 1
}
finally {
    try { Restore-Target } catch {}
    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }
    Stop-LocalTranscript
}
