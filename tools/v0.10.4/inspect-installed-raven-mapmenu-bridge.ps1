param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}

$game = [IO.Path]::GetFullPath($GameRoot)
$target = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    throw "Missing installed mapmenu override: $target"
}

$reportRel = 'archive/field-logs/completionist-v104-installed-raven-mapmenu-bridge.json'
$reportPath = Join-Path $repo ($reportRel -replace '/', '\')

$sha = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
$raw = [IO.File]::ReadAllBytes($target)
$text = [IO.File]::ReadAllText($target)
$lines = [regex]::Split($text, "\r?\n")

$needles = [ordered]@{
    candidate = 'Completionist_V103_Veithurgard_Raven_01'
    completionist_class = 'CompletionistRaven'
    marker_type_assignment = 'local markerType'
    dock_point_constant = 'COMPASS_MARKER_TYPE_DOCK_POINT'
    show_marker = 'game.Compass.ShowMarker'
    show_marker_candidate = 'game.Compass.ShowMarker(candidate'
    banner_v103_native = 'BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE'
    banner_v104_dedicated = 'BEGIN COMPLETIONIST V0.10.4 DEDICATED RAVEN COMPASS CLASS'
    prefix_v103 = '[CompletionistMap v0.10.3-native]'
    prefix_v104 = '[CompletionistMap v0.10.4-class]'
}

$hits = [ordered]@{}
foreach ($key in $needles.Keys) {
    $needle = [string]$needles[$key]
    $rows = @()
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Contains($needle)) {
            $rows += [ordered]@{
                line = $i + 1
                text = $lines[$i]
            }
        }
    }
    $hits[$key] = $rows
}

# Capture compact, deduplicated context around every Raven candidate and every
# candidate ShowMarker call. This is intentionally much smaller than mapmenu.lua.
$contextLineNumbers = New-Object 'System.Collections.Generic.HashSet[int]'
$anchorRows = @($hits.candidate) + @($hits.show_marker_candidate)
foreach ($row in $anchorRows) {
    $center = [int]$row.line
    $start = [Math]::Max(1, $center - 18)
    $end = [Math]::Min($lines.Count, $center + 24)
    for ($n = $start; $n -le $end; $n++) {
        [void]$contextLineNumbers.Add($n)
    }
}

$context = @()
foreach ($n in ($contextLineNumbers | Sort-Object)) {
    $context += [ordered]@{
        line = $n
        text = $lines[$n - 1]
    }
}

$counts = [ordered]@{}
foreach ($key in $needles.Keys) {
    $counts[$key] = @($hits[$key]).Count
}

$classification = 'UNRESOLVED'
if ($counts.banner_v104_dedicated -gt 0 -and $counts.completionist_class -gt 0) {
    $classification = 'V104_DEDICATED_BRIDGE_PRESENT'
} elseif ($counts.banner_v103_native -gt 0 -and $counts.dock_point_constant -gt 0) {
    $classification = 'V103_NATIVE_DOCKPOINT_BRIDGE_PRESENT'
} elseif ($counts.candidate -gt 0) {
    $classification = 'RAVEN_CANDIDATE_PRESENT_NONSTANDARD_BRIDGE'
} else {
    $classification = 'RAVEN_CANDIDATE_NOT_PRESENT'
}

$report = [ordered]@{
    result = 'READ_ONLY_INSTALLED_RAVEN_MAPMENU_BRIDGE_INSPECTED'
    classification = $classification
    mapmenu_sha256 = $sha
    mapmenu_bytes = $raw.Length
    line_count = $lines.Count
    counts = $counts
    hits = $hits
    context = $context
    safety = [ordered]@{
        game_files_read = $true
        game_files_written = $false
        wad_files_written = $false
        dcb_files_written = $false
        save_progression_marker_state_written = $false
        game_launched = $false
    }
}

$reportDir = Split-Path $reportPath -Parent
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
[IO.File]::WriteAllText(
    $reportPath,
    (($report | ConvertTo-Json -Depth 12) + "`n"),
    (New-Object Text.UTF8Encoding($false))
)

# Re-read the live file after inspection to prove the read-only probe itself did
# not alter it.
$shaAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
if ($shaAfter -ne $sha) {
    throw 'mapmenu.lua changed during read-only inspection.'
}

Write-Host 'READ_ONLY_INSTALLED_RAVEN_MAPMENU_BRIDGE_INSPECTED'
Write-Host ("  classification:              {0}" -f $classification)
Write-Host ("  mapmenu SHA256:              {0}" -f $sha)
Write-Host ("  candidate occurrences:       {0}" -f $counts.candidate)
Write-Host ("  CompletionistRaven hits:      {0}" -f $counts.completionist_class)
Write-Host ("  local markerType hits:        {0}" -f $counts.marker_type_assignment)
Write-Host ("  DockPoint constant hits:      {0}" -f $counts.dock_point_constant)
Write-Host ("  ShowMarker(candidate) hits:   {0}" -f $counts.show_marker_candidate)
Write-Host ("  v0.10.3 Raven banner hits:    {0}" -f $counts.banner_v103_native)
Write-Host ("  v0.10.4 Raven banner hits:    {0}" -f $counts.banner_v104_dedicated)
Write-Host '  game files written:           false'
Write-Host '  WAD/DCB files written:         false'
Write-Host ''
Write-Host 'Relevant Raven bridge context:'
if ($context.Count -eq 0) {
    Write-Host '  <no Raven candidate context found>'
} else {
    $previous = 0
    foreach ($row in $context) {
        $n = [int]$row.line
        if ($previous -ne 0 -and $n -gt ($previous + 1)) {
            Write-Host '  ...'
        }
        Write-Host ("  L{0}: {1}" -f $n, [string]$row.text)
        $previous = $n
    }
}
Write-Host ''
Write-Host ("Report: {0}" -f $reportPath)

# Archive only this generated report. Do not sweep unrelated staged/worktree
# changes into the diagnostic commit.
& git -C $repo add -- $reportRel
if ($LASTEXITCODE -ne 0) { throw 'git add failed for bridge-inspection report.' }
& git -C $repo diff --cached --quiet -- $reportRel
$hasReportChange = ($LASTEXITCODE -ne 0)
if ($hasReportChange) {
    & git -C $repo commit --only -m 'Archive installed Raven mapmenu bridge inspection' -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed for bridge-inspection report.' }
    & git -C $repo push origin $branch
    if ($LASTEXITCODE -ne 0) { throw 'git push failed for bridge-inspection report.' }
    Write-Host 'Bridge-inspection report committed and pushed.'
} else {
    Write-Host 'Bridge-inspection report unchanged; no commit needed.'
}
