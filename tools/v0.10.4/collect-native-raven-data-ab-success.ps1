param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War completely before collecting the successful native Raven data A/B.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
$ab = Join-Path $PSScriptRoot 'native-raven-data-ab.py'
if (-not (Test-Path -LiteralPath $ab -PathType Leaf)) { throw "Missing A/B tool: $ab" }

$stateRoot = Join-Path $repo 'build\v0.10.4\native-raven-no-render\ab-transactions'
if (-not (Test-Path -LiteralPath $stateRoot -PathType Container)) {
    throw "A/B transaction state directory missing: $stateRoot"
}

$installed = @()
Get-ChildItem -LiteralPath $stateRoot -Recurse -Filter manifest.json -File | ForEach-Object {
    try {
        $value = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
        if ([string]$value.kind -eq 'v104-native-raven-coordinate-graph-ab-v1' -and [string]$value.state -eq 'installed') {
            $installed += $_.FullName
        }
    } catch {
        # Ignore unrelated/malformed historical files; exact installed transaction count is checked below.
    }
}
if ($installed.Count -ne 1) {
    throw "Expected exactly one installed native Raven A/B transaction, found $($installed.Count)."
}
$manifest = [IO.Path]::GetFullPath($installed[0])
$manifestValue = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
$manifestSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifest).Hash.ToLowerInvariant()

$archiveRelPrefix = 'archive/field-logs/completionist-v104-native-raven-data-ab-'
$untracked = @(
    & git -C $repo ls-files --others --exclude-standard -- 'archive/field-logs/completionist-v104-native-raven-data-ab-*.json' |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
)
if ($LASTEXITCODE -ne 0) { throw 'git ls-files failed while checking recoverable A/B reports.' }

$report = $null
if ($untracked.Count -gt 0) {
    $matching = @()
    foreach ($candidateRelUnix in $untracked) {
        $candidate = Join-Path $repo ($candidateRelUnix.Replace('/', '\'))
        try {
            $evidence = Get-Content -LiteralPath $candidate -Raw | ConvertFrom-Json
            $evidenceManifestPath = [IO.Path]::GetFullPath([string]$evidence.manifest.path)
            $sameManifestPath = $evidenceManifestPath.Equals($manifest, [StringComparison]::OrdinalIgnoreCase)
            $sameManifestSha = ([string]$evidence.manifest.sha256).ToLowerInvariant() -eq $manifestSha
            $sameKind = [string]$evidence.transaction.kind -eq [string]$manifestValue.kind
            $sameState = [string]$evidence.transaction.state -eq 'installed'
            $sameInstalledUtc = [string]$evidence.transaction.installed_utc -eq [string]$manifestValue.installed_utc
            $sameResult = [string]$evidence.result -eq 'NATIVE_RAVEN_DATA_AB_CAPTURED_NOT_VISUAL_PROOF'
            $hudVisible = [string]$evidence.user_observation.hud -eq 'visible'
            if ($sameManifestPath -and $sameManifestSha -and $sameKind -and $sameState -and $sameInstalledUtc -and $sameResult -and $hudVisible) {
                $captured = [DateTimeOffset]::MinValue
                if (-not [DateTimeOffset]::TryParse([string]$evidence.captured_utc, [ref]$captured)) {
                    throw "Matching A/B report has invalid captured_utc: $candidate"
                }
                $matching += [pscustomobject]@{
                    Path = $candidate
                    Relative = $candidateRelUnix
                    CapturedUtc = $captured
                }
            }
        } catch {
            Write-Host "Ignoring non-matching/unreadable untracked A/B report: $candidateRelUnix"
        }
    }

    if ($matching.Count -gt 0) {
        $selected = @($matching | Sort-Object CapturedUtc, Relative -Descending)[0]
        $report = $selected.Path
        Write-Host "Reusing newest exact-match A/B evidence: $report"
        if ($matching.Count -gt 1) {
            Write-Host "  exact duplicate captures for this transaction: $($matching.Count)"
            Write-Host '  older duplicate capture(s) are left untouched and untracked.'
        }
    } else {
        throw ("Untracked A/B evidence exists, but none matches the exact active manifest/transaction:`n" + ($untracked -join "`n"))
    }
} else {
    $before = @(Get-ChildItem -LiteralPath (Join-Path $repo 'archive\field-logs') -Filter 'completionist-v104-native-raven-data-ab-*.json' -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)

    & $python.Source $ab --mode collect --game-root $GameRoot --manifest $manifest --hud visible --world unknown
    if ($LASTEXITCODE -ne 0) { throw 'Native Raven A/B evidence collection failed.' }

    $after = @(Get-ChildItem -LiteralPath (Join-Path $repo 'archive\field-logs') -Filter 'completionist-v104-native-raven-data-ab-*.json' -File | Select-Object -ExpandProperty FullName)
    $newFiles = @($after | Where-Object { $_ -notin $before })
    if ($newFiles.Count -ne 1) {
        throw "Expected exactly one new A/B evidence report, found $($newFiles.Count)."
    }
    $report = $newFiles[0]
}

# Windows PowerShell 5.1 runs on .NET Framework and does not expose
# System.IO.Path.GetRelativePath(). Compute the repo-relative path directly.
$repoFull = [IO.Path]::GetFullPath($repo).TrimEnd('\')
$reportFull = [IO.Path]::GetFullPath($report)
$prefix = $repoFull + '\'
if (-not $reportFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "A/B evidence report escaped the repository: $reportFull"
}
$rel = $reportFull.Substring($prefix.Length).Replace('\','/')
if (-not $rel.StartsWith($archiveRelPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unexpected A/B report path: $rel"
}

Push-Location $repo
try {
    git add -- $rel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $rel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git commit -m 'Archive successful native Raven data A/B' -- $rel
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    git push $Remote $branch
    if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host 'NATIVE_RAVEN_DATA_AB_SUCCESS_ARCHIVED'
Write-Host ("  manifest: {0}" -f $manifest)
Write-Host ("  report:   {0}" -f $report)
Write-Host '  user-observed HUD/native navigation: visible/working'
Write-Host '  world marker observation recorded as: unknown'
Write-Host '  A/B remains installed for the next class-only test'
