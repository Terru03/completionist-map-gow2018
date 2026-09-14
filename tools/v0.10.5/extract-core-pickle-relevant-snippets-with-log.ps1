param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relative = "archive/field-logs/source-scans/core-pickle-source-snippets-$stamp"
$outDir = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$result = Join-Path $outDir 'core-pickle-relevant-snippets.txt'
$meta = Join-Path $outDir 'metadata.txt'
$published = $false
$transcript = $false

function Publish([string]$Result) {
    if ($script:published) { return }
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        'source_file_copied=false'
        'game_launched=false'
        'save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'read_only=true'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

    & git add -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relative
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Archive focused core.pickle snippets $stamp" -- $relative | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin "HEAD:$expectedBranch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff failed.'
    }
    $script:published = $true
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true

    Write-Host '=== Completionist Map focused core.pickle source inspection ==='
    Write-Host 'Read-only. Archives only small relevant snippets; never copies the full game script.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing staged changes: $($staged -join ', ')" }

    $source = Join-Path $GameRoot 'mods\lua_source\gameart\scripts\libraries\core\pickle.lua'
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "core.pickle source missing: $source" }

    $hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $info = Get-Item -LiteralPath $source
    $lines = @(Get-Content -LiteralPath $source)

    @(
        "source=$source"
        "sha256=$hash"
        "bytes=$($info.Length)"
        "lines=$($lines.Count)"
        'full_source_archived=false'
    ) | Set-Content -LiteralPath $meta -Encoding UTF8

    # Research targets only. Merge overlapping windows and cap every window so
    # the archive contains only short excerpts from the copyrighted game source.
    $patterns = @(
        'OnPickleInternal', 'OnUnpickleInternal', 'CanPickle',
        '__PickleTable', '__SoftPickleTable', '__prevunpickle',
        'GameObject', 'userdata', 'Pickle', 'Unpickle'
    )

    $hitLines = New-Object 'System.Collections.Generic.HashSet[int]'
    for ($i = 0; $i -lt $lines.Count; $i++) {
        foreach ($p in $patterns) {
            if ($lines[$i] -match [regex]::Escape($p)) {
                [void]$hitLines.Add($i)
                break
            }
        }
    }

    $windows = @()
    foreach ($idx in ($hitLines | Sort-Object)) {
        $start = [Math]::Max(0, $idx - 4)
        $end = [Math]::Min($lines.Count - 1, $idx + 7)
        if ($windows.Count -eq 0 -or $start -gt ($windows[-1].End + 1)) {
            $windows += [pscustomobject]@{ Start = $start; End = $end }
        } else {
            $windows[-1].End = [Math]::Min($lines.Count - 1, [Math]::Max($windows[-1].End, $end))
        }
    }

    # Hard cap long merged regions to 40 source lines each. If a relevant area
    # is larger, split into bounded windows rather than archiving the whole file.
    $bounded = @()
    foreach ($w in $windows) {
        $s = $w.Start
        while ($s -le $w.End) {
            $e = [Math]::Min($w.End, $s + 39)
            $bounded += [pscustomobject]@{ Start = $s; End = $e }
            $s = $e + 1
        }
    }

    $out = New-Object 'System.Collections.Generic.List[string]'
    $out.Add('Completionist Map - focused core.pickle relevant snippets')
    $out.Add("source_sha256=$hash")
    $out.Add("source_lines=$($lines.Count)")
    $out.Add("matched_line_count=$($hitLines.Count)")
    $out.Add("snippet_windows=$($bounded.Count)")
    $out.Add('full_source_archived=false')
    $out.Add('')

    foreach ($w in $bounded) {
        $out.Add("--- lines $($w.Start + 1)-$($w.End + 1) ---")
        for ($i = $w.Start; $i -le $w.End; $i++) {
            $out.Add(('{0,5}: {1}' -f ($i + 1), $lines[$i]))
        }
        $out.Add('')
    }

    $out | Set-Content -LiteralPath $result -Encoding UTF8

    Write-Host "source_sha256=$hash"
    Write-Host "source_lines=$($lines.Count) matched_lines=$($hitLines.Count) snippet_windows=$($bounded.Count)"

    Publish 'SNIPPETS_CAPTURED'
    Write-Host 'CORE_PICKLE_SOURCE_SNIPPETS_CAPTURED_AND_PUSHED' -ForegroundColor Green
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "CAPTURE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish 'CAPTURE_FAILED' } catch { Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    if ($transcript) { try { Stop-Transcript | Out-Null } catch {} }
}
