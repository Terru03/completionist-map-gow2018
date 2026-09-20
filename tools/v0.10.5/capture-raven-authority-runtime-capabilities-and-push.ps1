param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $RepoRoot

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-authority-capabilities-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$console = Join-Path $outDir 'console-log.txt'
$probeExtract = Join-Path $outDir 'probe-extract.txt'
$targetRelative = 'mods\lua\gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$target = Join-Path $GameRoot $targetRelative
$probe = Join-Path $RepoRoot 'tools\v0.10.5\raven-authority-runtime-capability-probe.lua'
$loaderLog = Join-Path $GameRoot 'mods\loader_log.txt'
$exe = Join-Path $GameRoot 'GoW.exe'
$backup = Join-Path $env:TEMP "completionist-raven-authority-$stamp.bak"

$restored = $false
$published = $false
$transcript = $false
$launched = $false

function Restore-Target {
    if ($script:restored) { return }
    if (Test-Path -LiteralPath $backup -PathType Leaf) {
        [IO.File]::WriteAllBytes($target, [IO.File]::ReadAllBytes($backup))
        $script:restored = $true
    }
}

function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
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
        'marker_written_by_probe=false'
        'streaming_written_by_probe=false'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relativeDir
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "research(v0.10.5): capture Raven authority runtime capabilities $stamp" -- $relativeDir | Out-Host
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
    foreach ($path in @($target, $probe, $exe)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required file: $path" }
    }
    if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
        throw 'Close God of War before running this probe.'
    }

    $original = [IO.File]::ReadAllBytes($target)
    [IO.File]::WriteAllBytes($backup, $original)
    $beforeHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    $probeText = [IO.File]::ReadAllText($probe, [Text.Encoding]::UTF8)
    if ([Text.Encoding]::UTF8.GetString($original).Contains('BEGIN COMPLETIONIST RAVEN AUTHORITY CAPABILITY PROBE')) {
        throw 'Capability probe is already installed in precisionchallenge.lua.'
    }

    $append = [Text.Encoding]::UTF8.GetBytes("`r`n" + $probeText.Replace("`n", "`r`n"))
    $combined = New-Object byte[] ($original.Length + $append.Length)
    [Array]::Copy($original, 0, $combined, 0, $original.Length)
    [Array]::Copy($append, 0, $combined, $original.Length, $append.Length)
    [IO.File]::WriteAllBytes($target, $combined)

    $installedHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    @(
        "precisionchallenge_before_sha256=$beforeHash"
        "precisionchallenge_probe_installed_sha256=$installedHash"
        "probe_sha256=$((Get-FileHash -LiteralPath $probe -Algorithm SHA256).Hash.ToLowerInvariant())"
        "target=$target"
        'probe_read_only=true'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'installed-file-hashes.txt') -Encoding UTF8

    $beforeLines = @()
    if (Test-Path -LiteralPath $loaderLog -PathType Leaf) {
        $beforeLines = @(Get-Content -LiteralPath $loaderLog)
    }

    Write-Host 'RAVEN AUTHORITY CAPABILITY PROBE - READ ONLY'
    Write-Host 'God of War will launch now.'
    Write-Host 'Load your almost-done save, enter an area containing an Odin Raven script, and do not kill anything.'
    Write-Host 'Once the area has loaded, quit God of War fully.'
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

    $probeLines = @($fresh | Select-String -SimpleMatch '[CompletionistRavenAuthorityProbe]' | ForEach-Object { $_.Line })
    if ($probeLines.Count -gt 0) {
        $probeLines | Set-Content -LiteralPath $probeExtract -Encoding UTF8
    } else {
        'NO_COMPLETIONIST_RAVEN_AUTHORITY_PROBE_LINES_FOUND' | Set-Content -LiteralPath $probeExtract -Encoding UTF8
    }

    Restore-Target
    $afterHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    @(
        "precisionchallenge_before_sha256=$beforeHash"
        "precisionchallenge_after_restore_sha256=$afterHash"
        "exact_restore=$($afterHash -eq $beforeHash)"
    ) | Set-Content -LiteralPath (Join-Path $outDir 'restore-verification.txt') -Encoding UTF8
    if ($afterHash -ne $beforeHash) { throw 'precisionchallenge.lua restore hash mismatch.' }

    $hasCap = @($probeLines | Select-String -SimpleMatch ' CAP ').Count -gt 0
    $hasPickle = @($probeLines | Select-String -SimpleMatch 'PICKLE_SUMMARY').Count -gt 0
    $result = if ($hasCap -and $hasPickle) { 'RAVEN_AUTHORITY_CAPABILITIES_CAPTURED' } else { 'RAVEN_AUTHORITY_CAPABILITIES_INCOMPLETE' }
    Publish-Capture $result
    $head = (& git rev-parse HEAD).Trim()
    Write-Host "RAVEN_AUTHORITY_CAPABILITY_PUSHED $head" -ForegroundColor Green
    Write-Host "Evidence: $relativeDir"
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "RAVEN_AUTHORITY_CAPABILITY_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Restore-Target } catch {}
    try { Publish-Capture 'RAVEN_AUTHORITY_CAPABILITY_FAILED' } catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 1
}
finally {
    try { Restore-Target } catch {}
    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }
    Stop-LocalTranscript
}
