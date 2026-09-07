param(
    [ValidateSet('Prepare', 'Install', 'Remove')][string]$Mode = 'Prepare',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$game = [IO.Path]::GetFullPath($GameRoot)
$relative = 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$target = Join-Path $game $relative
$stateDir = Join-Path $repo 'build\v0.10.3-lookup'
$manifestPath = Join-Path $stateDir 'active.json'
$utf8 = New-Object Text.UTF8Encoding($false)

function Hash-File([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }

if ((git -C $repo branch --show-current) -ne 'research/v0.10.3-native-compass') {
    throw 'Use research/v0.10.3-native-compass branch.'
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close game before prepare, install, or rollback.'
}
if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Override missing: $target" }
if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'No active probe manifest.' }
    $saved = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $backup = [IO.Path]::GetFullPath([string]$saved.backup)
    if ($saved.target -ne $target -or (Split-Path $backup -Parent) -ne $stateDir) {
        throw 'Manifest path mismatch. Restore manually from known backup.'
    }
    if ((Hash-File $target) -ne $saved.after -or (Hash-File $backup) -ne $saved.before) {
        throw 'Files changed after install. Refuse overwrite; preserve newer edits.'
    }
    Copy-Item -LiteralPath $backup -Destination $target
    if ((Hash-File $target) -ne $saved.before) { throw 'Rollback hash mismatch.' }
    Move-Item -LiteralPath $manifestPath -Destination (Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json'))
    Write-Host 'v0.10.3 lookup probe removed. Original override restored byte-for-byte.'
    return
}
$exe = Join-Path $game 'GoW.exe'
if (-not (Test-Path -LiteralPath $exe) -or
    (Hash-File $exe) -ne 'CAEBCB027980D7EAC9203D190F9EE649EEBC549F8DEFCE138E2114DC91F40452') {
    throw 'Executable differs from inspected build. Refuse native lookup probe.'
}
if (Test-Path -LiteralPath $manifestPath) { throw 'Probe already installed. Remove first.' }
$source = [IO.File]::ReadAllText($target)
if ($source.Contains('BEGIN COMPLETIONIST V0.10.3')) { throw 'Probe already in override.' }
if (-not $source.Contains('[CompletionistMap v0.10.1]') -or
    ([regex]::Matches($source, 'function MapOn:GetRealmMarkerInfo\(\)')).Count -ne 1) {
    throw 'Expected tested Completionist map override not found.'
}
$probe = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'native-lookup-probe.lua'))
$before = Hash-File $target
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$prepared = Join-Path $stateDir 'mapmenu.lua'
[IO.File]::WriteAllText($prepared, $source + "`r`n" + $probe, $utf8)
Write-Host "Prepared read-only probe: $prepared"
if ($Mode -eq 'Prepare') { return }
if ((Hash-File $target) -ne $before) { throw 'Override changed during prepare. Refuse install.' }
$backup = Join-Path $stateDir ('mapmenu-' + [Guid]::NewGuid().ToString('N') + '.bak')
Copy-Item -LiteralPath $target -Destination $backup
if ((Hash-File $backup) -ne $before) { throw 'Backup hash mismatch.' }
$after = Hash-File $prepared
# Save recovery path before write.
$manifest = [ordered]@{ target = $target; backup = $backup; before = $before; after = $after }
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json), $utf8)
try {
    Copy-Item -LiteralPath $prepared -Destination $target
    if ((Hash-File $target) -ne $after) { throw 'Installed hash mismatch.' }
} catch {
    Copy-Item -LiteralPath $backup -Destination $target
    Move-Item -LiteralPath $manifestPath -Destination (Join-Path $stateDir ('failed-' + [Guid]::NewGuid().ToString('N') + '.json'))
    throw
}
Write-Host 'v0.10.3 read-only probe installed. Launch game yourself; open Midgard map once.'
Write-Host 'No ShowMarker call. Existing HUD remains prototype.'
Write-Host "Log: $(Join-Path $game 'mods\loader_log.txt')"
Write-Host "Rollback: powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Mode Remove"
