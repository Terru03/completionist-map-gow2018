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
    throw 'Close God of War before installing or removing the Raven map-class slot proof.'
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
    if ($current -ne $Before) { Copy-Item -LiteralPath $Backup -Destination $Target -Force }
    if ((Hash $Target) -ne $Before) { throw "Rollback hash mismatch: $Target" }
}

$game = [IO.Path]::GetFullPath($GameRoot)
$mapmaster = Join-Path $game 'exec\dc\pc_le\mapmaster.dcb'
$ruiWad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$ruiDcb = Join-Path $game 'exec\dc\pc_le\wad_r_ui.dcb'
$mapmenu = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$boot = Join-Path $game 'exec\boot-options.json'

$mapPatcher = Join-Path $PSScriptRoot 'patch-native-raven-map-icon.py'
$slotPatcher = Join-Path $PSScriptRoot 'patch-r-ui-gopool-slot.py'
$luaBridge = Join-Path $PSScriptRoot 'raven-map-class-slot-proof.lua'
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-map-class-slot'
$manifestPath = Join-Path $stateDir 'active.json'
$backupDir = Join-Path $stateDir 'backup'
$patchedMapmaster = Join-Path $stateDir 'mapmaster-raven-slot.dcb'
$patchedRuiDcb = Join-Path $stateDir 'wad_r_ui-raven-slot.dcb'
$mapPatchReport = Join-Path $stateDir 'mapmaster-patch.json'
$slotPatchReport = Join-Path $stateDir 'gopool-slot-patch.json'
$utf8 = New-Object Text.UTF8Encoding($false)

$oldVisualManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-map-visual-proof\active.json'
$oldControlManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-map-class-control\active.json'

$expectedNativeMapmaster = '1e076f7c5f0aea8d93ad72365bcaa267361503eee10fcdab0522c699b188508a'
$stockRuiWad = '92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04'
$stockRuiDcb = '21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a'
$oldSlotName = 'goMapIconValkyrie_location'
$newSlotName = 'goMapIconCompletionistRaven'

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Raven map-class slot proof is already removed.'
        return
    }
    $m = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    Restore-ProofFile $mapmaster (Join-Path $backupDir 'mapmaster.dcb') ([string]$m.mapmaster_before) ([string]$m.mapmaster_after)
    Restore-ProofFile $ruiDcb (Join-Path $backupDir 'wad_r_ui.dcb') ([string]$m.rui_dcb_before) ([string]$m.rui_dcb_after)
    Restore-ProofFile $mapmenu (Join-Path $backupDir 'mapmenu.lua') ([string]$m.mapmenu_before) ([string]$m.mapmenu_after)
    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Raven map-class slot proof removed.'
    Write-Host 'The v0.10.3 native Raven baseline and stock WAD_R_UI DCB were restored exactly.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Raven map-class slot proof is already installed.'
}
if (Test-Path -LiteralPath $oldVisualManifest -PathType Leaf) {
    throw 'The crashing custom-WAD Raven visual proof is still active. Remove it first.'
}
if (Test-Path -LiteralPath $oldControlManifest -PathType Leaf) {
    throw 'The Valkyrie map-class control proof is still active. Remove it first.'
}
foreach ($required in @($mapmaster,$ruiWad,$ruiDcb,$mapmenu,$boot,$mapPatcher,$slotPatcher,$luaBridge)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}
if ((Hash $mapmaster) -ne $expectedNativeMapmaster) {
    throw 'mapmaster.dcb is not the tested v0.10.3 native Raven baseline.'
}
if ((Hash $ruiWad) -ne $stockRuiWad) {
    throw 'r_ui.wad is not stock. Do not run this proof until the crashing custom-WAD proof is removed.'
}
if ((Hash $ruiDcb) -ne $stockRuiDcb) {
    throw 'wad_r_ui.dcb is not stock.'
}

$bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
$patches = @($bootObj.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
foreach ($entry in $patches) {
    if ([string]$entry -match '(?i)completionist_v104_raven_map|dock[_-]?raven|0Completionist_v102_dock_raven') {
        throw "A Raven/Dock visual texpack is still registered: $entry"
    }
}

$mapText = [IO.File]::ReadAllText($mapmenu)
if (-not $mapText.Contains('BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE')) {
    throw 'The tested v0.10.3 native Raven production bridge is not active.'
}
if ($mapText.Contains('BEGIN COMPLETIONIST V0.10.4 RAVEN MAP CLASS SLOT PROOF')) {
    throw 'Raven map-class slot proof Lua already appears installed.'
}

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
& $python.Source -m py_compile $mapPatcher $slotPatcher
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed.' }

& $python.Source $mapPatcher `
    --input $mapmaster `
    --output $patchedMapmaster `
    --report $mapPatchReport `
    --expected-old-icon 'goMapIconDock' `
    --new-icon $newSlotName | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Raven mapmaster class-name patch failed.' }

& $python.Source $slotPatcher `
    --input $ruiDcb `
    --output $patchedRuiDcb `
    --report $slotPatchReport `
    --old-name $oldSlotName `
    --new-name $newSlotName | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'WAD_R_UI GOPool slot rename failed.' }

$slotInfo = Get-Content -LiteralPath $slotPatchReport -Raw | ConvertFrom-Json
if ($slotInfo.only_name_hash_bytes_changed -ne $true -or
    $slotInfo.file_size_preserved -ne $true -or
    $slotInfo.cnt_preserved -ne 9 -or
    $slotInfo.new_name -ne $newSlotName) {
    throw 'GOPool slot patch report failed validation.'
}
if ((Hash $ruiWad) -ne $stockRuiWad) { throw 'r_ui.wad changed during offline preparation.' }

Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$mapmasterBackup = Join-Path $backupDir 'mapmaster.dcb'
$ruiDcbBackup = Join-Path $backupDir 'wad_r_ui.dcb'
$mapmenuBackup = Join-Path $backupDir 'mapmenu.lua'
Copy-Item -LiteralPath $mapmaster -Destination $mapmasterBackup
Copy-Item -LiteralPath $ruiDcb -Destination $ruiDcbBackup
Copy-Item -LiteralPath $mapmenu -Destination $mapmenuBackup

$beforeMapmaster = Hash $mapmaster
$beforeRuiDcb = Hash $ruiDcb
$beforeMapmenu = Hash $mapmenu
try {
    Copy-Item -LiteralPath $patchedMapmaster -Destination $mapmaster -Force
    Copy-Item -LiteralPath $patchedRuiDcb -Destination $ruiDcb -Force
    $bridge = [IO.File]::ReadAllText($luaBridge)
    [IO.File]::WriteAllText($mapmenu, $mapText + "`r`n" + $bridge + "`r`n", $utf8)

    $afterMapmaster = Hash $mapmaster
    $afterRuiDcb = Hash $ruiDcb
    $afterMapmenu = Hash $mapmenu
    if ($afterMapmaster -eq $beforeMapmaster) { throw 'mapmaster was not changed.' }
    if ($afterRuiDcb -eq $beforeRuiDcb) { throw 'wad_r_ui.dcb was not changed.' }
    if ($afterMapmenu -eq $beforeMapmenu) { throw 'mapmenu was not changed.' }
    if ((Hash $ruiWad) -ne $stockRuiWad) { throw 'r_ui.wad changed during a DCB-only proof.' }

    $manifest = [ordered]@{
        proof = 'v0.10.4 custom map-class name via existing GOPool slot'
        candidate = 'Completionist_V103_Veithurgard_Raven_01'
        map_resource = $newSlotName
        donor_slot = $oldSlotName
        donor_cnt = 9
        compass_type = 'DockPoint'
        r_ui_wad_unchanged = $true
        texpack_loaded = $false
        mapmaster_before = $beforeMapmaster
        mapmaster_after = $afterMapmaster
        rui_dcb_before = $beforeRuiDcb
        rui_dcb_after = $afterRuiDcb
        mapmenu_before = $beforeMapmenu
        mapmenu_after = $afterMapmenu
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8) + [Environment]::NewLine, $utf8)
}
catch {
    Write-Warning "Slot proof install failed. Restoring pre-proof files: $($_.Exception.Message)"
    try {
        Copy-Item -LiteralPath $mapmasterBackup -Destination $mapmaster -Force
        Copy-Item -LiteralPath $ruiDcbBackup -Destination $ruiDcb -Force
        Copy-Item -LiteralPath $mapmenuBackup -Destination $mapmenu -Force
    } catch {
        Write-Warning "Automatic recovery also failed: $($_.Exception.Message)"
    }
    throw
}

$reportRel = 'archive/field-logs/completionist-v104-raven-map-class-slot-install.json'
$reportPath = Join-Path $repo ($reportRel -replace '/', '\')
$installReport = [ordered]@{
    result = 'RAVEN_MAP_CLASS_SLOT_PROOF_INSTALLED'
    installed_into_game = $true
    candidate = 'Completionist_V103_Veithurgard_Raven_01'
    map_resource = $newSlotName
    donor_slot = $oldSlotName
    donor_visual_expected = 'stock Valkyrie artwork'
    compass_type = 'DockPoint'
    r_ui_wad_stock = ((Hash $ruiWad) -eq $stockRuiWad)
    texpack_loaded = $false
    save_state_written = $false
    progression_state_written = $false
    native_kratos_marker_touched = $false
    slot_patch = $slotInfo
    reversible_manifest = $manifestPath
}
New-Item -ItemType Directory -Force -Path (Split-Path $reportPath -Parent) | Out-Null
[IO.File]::WriteAllText($reportPath, ($installReport | ConvertTo-Json -Depth 20) + [Environment]::NewLine, $utf8)

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for slot proof report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven map class slot install' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for slot proof report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Slot proof installed, but pushing its report failed.' }
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Raven custom map-class SLOT proof installed.'
Write-Host '- map class name: goMapIconCompletionistRaven'
Write-Host '- temporary donor slot: goMapIconValkyrie_location'
Write-Host '- r_ui.wad: STOCK and untouched'
Write-Host '- no texpack loaded'
Write-Host '- no Dock map proxy used'
Write-Host '- compass/navigation remains DockPoint for now'
Write-Host ''
Write-Host 'Launch God of War and open Midgard / Veithurgard.'
Write-Host 'Expected: Raven appears with stock Valkyrie artwork through the CUSTOM class name, without the grey-map/crash behaviour caused by the grown WAD.'
Write-Host ("Rollback: powershell -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
