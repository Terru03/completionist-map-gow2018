param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin',
    [switch]$RemoveAfter
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War completely before collecting the Raven native route re-proof.'
}

$stateDir = Join-Path $repo 'build\v0.10.4-raven-native-route-reproof'
$manifestPath = Join-Path $stateDir 'active.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw 'Native route re-proof is not active. Nothing authoritative to collect.'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ([string]$manifest.kind -ne 'completionist-v104-raven-native-route-reproof') {
    throw 'Unexpected route re-proof manifest kind.'
}

$mapTarget = Join-Path ([IO.Path]::GetFullPath($GameRoot)) 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
if (-not (Test-Path -LiteralPath $mapTarget -PathType Leaf)) { throw "Missing mapmenu.lua: $mapTarget" }
$currentMapHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $mapTarget).Hash.ToLowerInvariant()
if ($currentMapHash -ne ([string]$manifest.map_after_sha256).ToLowerInvariant()) {
    throw 'Installed mapmenu.lua no longer matches the active route re-proof. Refusing to archive mixed-state evidence.'
}

$log = Join-Path $GameRoot 'mods\loader_log.txt'
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { throw "Loader log missing: $log" }
$lines = @(
    Select-String -LiteralPath $log -SimpleMatch '[CompletionistMap v0.10.3-native]' |
        ForEach-Object { $_.Line.TrimEnd() }
)
if ($lines.Count -eq 0) {
    throw 'No native Raven route lines found in loader_log.txt. Launch/test the game first.'
}

$showBefore = @($lines | Where-Object { $_ -match 'NATIVE_RAVEN_SHOW stage=before' }).Count
$showOK = @($lines | Where-Object { $_ -match 'NATIVE_RAVEN_SHOW stage=lua_return ok=true' }).Count
$showFail = @($lines | Where-Object { $_ -match 'NATIVE_RAVEN_SHOW stage=lua_return ok=false' }).Count
$queued = @($lines | Where-Object { $_ -match 'NATIVE_RAVEN_RESULT request_queued=true active=true' }).Count
$verified = @($lines | Where-Object { $_ -match 'NATIVE_RAVEN_VERIFY active=true' }).Count
$legacyDisabled = @($lines | Where-Object { $_ -match 'LEGACY_R3L3_DISABLED' }).Count
$api = @($lines | Where-Object { $_ -match 'NATIVE_RAVEN_API installed=true' }).Count

$result = if ($showBefore -gt 0 -and $showOK -gt 0 -and $showFail -eq 0 -and $queued -gt 0 -and $verified -gt 0) {
    'NATIVE_RAVEN_ROUTE_MANAGER_ACCEPTED'
} elseif ($showBefore -gt 0 -and $showFail -gt 0) {
    'NATIVE_RAVEN_ROUTE_SHOWMARKER_FAILED'
} else {
    'NATIVE_RAVEN_ROUTE_RUNTIME_INCOMPLETE'
}

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v104-native-raven-route-reproof.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
$header = @(
    'Completionist Map v0.10.4 native Raven route re-proof'
    ('Captured UTC: ' + [DateTime]::UtcNow.ToString('o'))
    ('Result: ' + $result)
    ('Candidate: ' + [string]$manifest.marker)
    ('Candidate ID: ' + [string]$manifest.marker_id_hex)
    ('Compass type: ' + [string]$manifest.compass_type)
    ('Installed mapmenu SHA256: ' + $currentMapHash)
    ('API lines: ' + $api)
    ('Show-before lines: ' + $showBefore)
    ('Show-return-ok lines: ' + $showOK)
    ('Show-return-fail lines: ' + $showFail)
    ('Requests queued: ' + $queued)
    ('Manager verification lines: ' + $verified)
    ('Legacy R3/L3 suppression lines: ' + $legacyDisabled)
    'WAD/DCB files changed by route re-proof installer: false'
    'Save/progression/marker-state changed by route re-proof installer: false'
    ''
    '=== native Raven route log ==='
)
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out, @($header + $lines), $utf8)

Write-Host "Saved native Raven route re-proof: $out"
Write-Host "Result: $result"
Write-Host "ShowMarker returns OK: $showOK"
Write-Host "Manager verification lines: $verified"
Write-Host "Legacy R3/L3 suppressions: $legacyDisabled"

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Route re-proof report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive native Raven route re-proof' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Pushed route re-proof report to $Remote/$branch"
    }
} finally {
    Pop-Location
}

if ($RemoveAfter) {
    & (Join-Path $PSScriptRoot 'install-raven-native-route-reproof.ps1') -Mode Remove -GameRoot $GameRoot
}
