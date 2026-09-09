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
    throw 'God of War is still running. Close it completely before collecting crash evidence.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$stateDir = Join-Path $repo 'build\v0.10.4-raven-native-custom-class-control'
$manifestPath = Join-Path $stateDir 'active.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw 'Native custom-class control is not active; refusing to label unrelated logs as this crash.'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ([string]$manifest.kind -ne 'completionist-v104-raven-native-custom-class-control') {
    throw 'Unexpected custom-class manifest kind.'
}

function Hash-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

$map = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$coords = Join-Path $game 'exec\dc\pc_le\mapcoords.dcb'
$graph = Join-Path $game 'exec\dc\pc_le\compassgraph.dcb'
$perm = Join-Path $game 'exec\dc\pc_le\wad_r_perm.dcb'
$wad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$log = Join-Path $game 'mods\loader_log.txt'

$currentMap = Hash-File $map
if ($currentMap -ne ([string]$manifest.map_after_sha256).ToLowerInvariant()) {
    throw 'mapmenu.lua no longer matches the crashing custom-class control; refusing mixed-state capture.'
}
if ((Hash-File $coords) -ne ([string]$manifest.mapcoords_sha256).ToLowerInvariant()) { throw 'mapcoords.dcb changed after class control install.' }
if ((Hash-File $graph) -ne ([string]$manifest.compassgraph_sha256).ToLowerInvariant()) { throw 'compassgraph.dcb changed after class control install.' }
if ((Hash-File $perm) -ne ([string]$manifest.wad_r_perm_sha256).ToLowerInvariant()) { throw 'wad_r_perm.dcb changed after class control install.' }
if ((Hash-File $wad) -ne ([string]$manifest.r_ui_wad_sha256).ToLowerInvariant()) { throw 'r_ui.wad changed after class control install.' }
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { throw "Missing loader log: $log" }

# Normalize only trailing whitespace from copied log lines so the archived evidence
# remains readable while also satisfying git diff --check. The source loader log is
# never modified.
$all = @(Get-Content -LiteralPath $log | ForEach-Object { $_.TrimEnd() })
# Use literal substring checks. PowerShell -like treats '[' as a wildcard character-class opener.
$native = @($all | Where-Object { $_.Contains('[CompletionistMap v0.10.3-native]') })
$completionist = @($all | Where-Object { $_.Contains('[CompletionistMap') })
$tail = @($all | Select-Object -Last 180)

$showBeforeCustom = @($native | Where-Object { $_ -match 'NATIVE_RAVEN_SHOW stage=before' -and $_ -match 'markerType=CompletionistRaven' }).Count
$showReturn = @($native | Where-Object { $_ -match 'NATIVE_RAVEN_SHOW stage=lua_return' }).Count
$showReturnOK = @($native | Where-Object { $_ -match 'NATIVE_RAVEN_SHOW stage=lua_return ok=true' }).Count
$verify = @($native | Where-Object { $_ -match 'NATIVE_RAVEN_VERIFY active=true' }).Count

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v104-native-custom-class-crash.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
$header = @(
    'Completionist Map v0.10.4 native custom-class crash capture'
    ('Captured UTC: ' + [DateTime]::UtcNow.ToString('o'))
    'User observation: CRASHED when adding the authored Raven to compass'
    'Control delta: native ShowMarker markerType DockPoint -> CompletionistRaven'
    ('Installed control UTC: ' + [string]$manifest.installed_utc)
    ('mapmenu SHA256: ' + $currentMap)
    ('mapcoords SHA256: ' + (Hash-File $coords))
    ('compassgraph SHA256: ' + (Hash-File $graph))
    ('wad_r_perm SHA256: ' + (Hash-File $perm))
    ('r_ui.wad SHA256: ' + (Hash-File $wad))
    ('Custom Show-before lines: ' + $showBeforeCustom)
    ('All native Show-return lines in log: ' + $showReturn)
    ('All native Show-return-ok lines in log: ' + $showReturnOK)
    ('All native manager-verify lines in log: ' + $verify)
    'Native coordinate/graph A/B remains installed and was previously user-proven to route/pathfind with DockPoint.'
    'No save/progression/marker-state files touched by collector.'
    ''
    '=== all v0.10.3-native lines ==='
)
$body = @($header + $native + @('', '=== recent CompletionistMap lines ===') + $completionist + @('', '=== loader log tail (180 lines) ===') + $tail)
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out, $body, $utf8)

Write-Host "Saved custom-class crash evidence: $out"
Write-Host "Custom Show-before lines: $showBeforeCustom"
Write-Host "Native Show-return lines in current loader log: $showReturn"
Write-Host "Native manager-verify lines in current loader log: $verify"

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Crash report unchanged; nothing to commit.'
    } else {
        git commit -m 'Archive native Raven custom-class crash' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Pushed crash evidence to $Remote/$branch"
    }
} finally {
    Pop-Location
}
