param(
    [ValidateSet('Install','Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') {
    throw "Expected feat/v0.10.4-all-ravens, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the Raven map-class control proof.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

function Hash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Restore-ProofFile([string]$Target, [string]$Backup, [string]$Before, [string]$After) {
    if (-not (Test-Path -LiteralPath $Backup -PathType Leaf)) { throw "Missing backup: $Backup" }
    if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) { throw "Missing current target: $Target" }
    $current = Hash $Target
    if ($current -ne $Before -and $current -ne $After) {
        throw "$Target changed after proof installation. Refusing automatic overwrite."
    }
    if ($current -ne $Before) {
        Copy-Item -LiteralPath $Backup -Destination $Target -Force
    }
    if ((Hash $Target) -ne $Before) { throw "Rollback hash mismatch: $Target" }
}

$game = [IO.Path]::GetFullPath($GameRoot)
$mapmaster = Join-Path $game 'exec\dc\pc_le\mapmaster.dcb'
$ruiWad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$ruiDcb = Join-Path $game 'exec\dc\pc_le\wad_r_ui.dcb'
$mapmenu = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$boot = Join-Path $game 'exec\boot-options.json'

$patcher = Join-Path $PSScriptRoot 'patch-native-raven-map-icon.py'
$luaBridge = Join-Path $PSScriptRoot 'raven-map-class-control-proof.lua'
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-map-class-control'
$manifestPath = Join-Path $stateDir 'active.json'
$backupDir = Join-Path $stateDir 'backup'
$patchedMapmaster = Join-Path $stateDir 'mapmaster-valkyrie-control.dcb'
$patchReport = Join-Path $stateDir 'mapmaster-patch.json'
$oldVisualManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-map-visual-proof\active.json'
$utf8 = New-Object Text.UTF8Encoding($false)

# Baseline is the already field-proven v0.10.3 authored Raven DCB install.
$expectedNativeMapmaster = '1e076f7c5f0aea8d93ad72365bcaa267361503eee10fcdab0522c699b188508a'
$stockRuiWad = '92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04'
$stockRuiDcb = '21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a'
$controlResource = 'goMapIconValkyrie_location'

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Raven map-class control proof is already removed.'
        return
    }
    $m = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    Restore-ProofFile $mapmaster (Join-Path $backupDir 'mapmaster.dcb') ([string]$m.mapmaster_before) ([string]$m.mapmaster_after)
    Restore-ProofFile $mapmenu (Join-Path $backupDir 'mapmenu.lua') ([string]$m.mapmenu_before) ([string]$m.mapmenu_after)
    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Raven map-class control proof removed.'
    Write-Host 'The v0.10.3 native Raven baseline was restored exactly.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Raven map-class control proof is already installed.'
}
if (Test-Path -LiteralPath $oldVisualManifest -PathType Leaf) {
    throw 'The earlier v0.10.4 Raven visual proof is still active. Remove it first with install-raven-map-visual-proof.ps1 -Mode Remove.'
}
foreach ($required in @($mapmaster,$ruiWad,$ruiDcb,$mapmenu,$boot,$patcher,$luaBridge)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}
if ((Hash $mapmaster) -ne $expectedNativeMapmaster) {
    throw 'mapmaster.dcb is not the tested v0.10.3 native Raven baseline. Refusing the control proof.'
}
if ((Hash $ruiWad) -ne $stockRuiWad -or (Hash $ruiDcb) -ne $stockRuiDcb) {
    throw 'r_ui.wad / wad_r_ui.dcb are not stock. Remove the failed v0.10.4 visual proof before this control test.'
}

$mapText = [IO.File]::ReadAllText($mapmenu)
if (-not $mapText.Contains('BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE')) {
    throw 'The tested v0.10.3 native Raven production bridge is not active.'
}
if ($mapText.Contains('BEGIN COMPLETIONIST V0.10.4 RAVEN MAP VISUAL PROOF')) {
    throw 'Old Raven visual proof Lua is still active. Roll it back before this test.'
}
if ($mapText.Contains('BEGIN COMPLETIONIST V0.10.4 RAVEN MAP CLASS CONTROL PROOF')) {
    throw 'Raven map-class control Lua already appears installed.'
}

$bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
$patches = @($bootObj.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
foreach ($entry in $patches) {
    if ([string]$entry -match '(?i)completionist_v104_raven_map|dock[_-]?raven|0Completionist_v102_dock_raven') {
        throw "A Raven/Dock visual texpack is still registered: $entry. Roll back that proof first."
    }
}

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
& $python.Source -m py_compile $patcher
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed for native Raven map-icon patcher.' }

& $python.Source $patcher `
    --input $mapmaster `
    --output $patchedMapmaster `
    --report $patchReport `
    --expected-old-icon 'goMapIconDock' `
    --new-icon $controlResource | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Stock-class control mapmaster patch failed.' }
if (-not (Test-Path -LiteralPath $patchedMapmaster -PathType Leaf)) { throw 'Control mapmaster was not produced.' }
$patchInfo = Get-Content -LiteralPath $patchReport -Raw | ConvertFrom-Json
if ($patchInfo.new_icon -ne $controlResource -or $patchInfo.old_icon -ne 'goMapIconDock' -or $patchInfo.relocation_preserved -ne $true) {
    throw 'Control mapmaster patch report failed validation.'
}

Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$mapmasterBackup = Join-Path $backupDir 'mapmaster.dcb'
$mapmenuBackup = Join-Path $backupDir 'mapmenu.lua'
Copy-Item -LiteralPath $mapmaster -Destination $mapmasterBackup
Copy-Item -LiteralPath $mapmenu -Destination $mapmenuBackup
if ((Hash $mapmasterBackup) -ne (Hash $mapmaster)) { throw 'mapmaster backup hash mismatch.' }
if ((Hash $mapmenuBackup) -ne (Hash $mapmenu)) { throw 'mapmenu backup hash mismatch.' }

$beforeMapmaster = Hash $mapmaster
$beforeMapmenu = Hash $mapmenu
try {
    Copy-Item -LiteralPath $patchedMapmaster -Destination $mapmaster -Force
    $bridge = [IO.File]::ReadAllText($luaBridge)
    [IO.File]::WriteAllText($mapmenu, $mapText + "`r`n" + $bridge + "`r`n", $utf8)

    $afterMapmaster = Hash $mapmaster
    $afterMapmenu = Hash $mapmenu
    if ($afterMapmaster -eq $beforeMapmaster) { throw 'mapmaster was not changed by control proof.' }
    if ($afterMapmenu -eq $beforeMapmenu) { throw 'mapmenu was not changed by control proof.' }
    if (-not ([IO.File]::ReadAllText($mapmenu).Contains('BEGIN COMPLETIONIST V0.10.4 RAVEN MAP CLASS CONTROL PROOF'))) {
        throw 'Control Lua bridge missing after write.'
    }
    if ((Hash $ruiWad) -ne $stockRuiWad -or (Hash $ruiDcb) -ne $stockRuiDcb) {
        throw 'UI WAD/DCB changed during a proof that must not touch them.'
    }

    $manifest = [ordered]@{
        proof = 'v0.10.4 direct authored map-class stock control'
        candidate = 'Completionist_V103_Veithurgard_Raven_01'
        map_resource = $controlResource
        compass_type = 'DockPoint'
        dock_proxy_used = $false
        mapmaster_before = $beforeMapmaster
        mapmaster_after = $afterMapmaster
        mapmenu_before = $beforeMapmenu
        mapmenu_after = $afterMapmenu
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8) + [Environment]::NewLine, $utf8)
}
catch {
    Write-Warning "Control proof install failed. Restoring pre-proof files: $($_.Exception.Message)"
    try {
        Copy-Item -LiteralPath $mapmasterBackup -Destination $mapmaster -Force
        Copy-Item -LiteralPath $mapmenuBackup -Destination $mapmenu -Force
    } catch {
        Write-Warning "Automatic recovery also failed: $($_.Exception.Message)"
    }
    throw
}

$reportRel = 'archive/field-logs/completionist-v104-raven-map-class-control-install.json'
$reportPath = Join-Path $repo ($reportRel -replace '/', '\')
$report = [ordered]@{
    result = 'RAVEN_MAP_CLASS_CONTROL_INSTALLED'
    installed_into_game = $true
    purpose = 'Prove map Icon resource independence from DockPoint compass/navigation class'
    candidate = 'Completionist_V103_Veithurgard_Raven_01'
    map_resource_control = $controlResource
    compass_type = 'DockPoint'
    dock_proxy_used = $false
    custom_wad_loaded = $false
    texpack_loaded = $false
    r_ui_wad_stock = ((Hash $ruiWad) -eq $stockRuiWad)
    wad_r_ui_dcb_stock = ((Hash $ruiDcb) -eq $stockRuiDcb)
    save_state_written = $false
    progression_state_written = $false
    native_kratos_marker_touched = $false
    patch = $patchInfo
    mapmaster_before = $beforeMapmaster
    mapmaster_after = $afterMapmaster
    mapmenu_before = $beforeMapmenu
    mapmenu_after = $afterMapmenu
    reversible_manifest = $manifestPath
}
New-Item -ItemType Directory -Force -Path (Split-Path $reportPath -Parent) | Out-Null
[IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 20) + [Environment]::NewLine, $utf8)

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for control proof report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven map class control install' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for control proof report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Control proof installed, but pushing its report failed.' }
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Raven direct map-class CONTROL proof installed.'
Write-Host '- Raven map Icon resource: goMapIconValkyrie_location (stock control)'
Write-Host '- Raven compass/navigation class: DockPoint (unchanged)'
Write-Host '- Dock proxy creation: DISABLED'
Write-Host '- r_ui.wad / wad_r_ui.dcb: stock and untouched'
Write-Host '- no Raven texpack loaded'
Write-Host ''
Write-Host 'Launch the game and open Midgard / Veithurgard.'
Write-Host 'Expected control result: the Completionist Raven appears with stock Valkyrie artwork while real docks remain Dock artwork.'
Write-Host 'If there is NO Raven marker, that is also useful evidence; do not substitute or reinstall a Dock texture proof.'
Write-Host ("Rollback: powershell -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
