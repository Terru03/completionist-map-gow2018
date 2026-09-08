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
    throw 'Close God of War before installing or removing the registered Raven runtime proof.'
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

$work = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.4\raven-ui-registered-class'
$candidateWad = Join-Path $work 'r_ui.wad'
$candidateDcb = Join-Path $work 'wad_r_ui.dcb'
$buildReport = Join-Path $repo 'archive\field-logs\completionist-v104-raven-ui-registered-class.json'
$resolutionReport = Join-Path $repo 'archive\field-logs\completionist-v104-raven-ui-registered-resolution.json'

$patcher = Join-Path $PSScriptRoot 'patch-native-raven-map-icon.py'
$luaBridge = Join-Path $PSScriptRoot 'raven-registered-class-runtime-proof.lua'
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-registered-class-runtime'
$manifestPath = Join-Path $stateDir 'active.json'
$backupDir = Join-Path $stateDir 'backup'
$patchedMapmaster = Join-Path $stateDir 'mapmaster-raven-registered-runtime.dcb'
$patcherReport = Join-Path $stateDir 'mapmaster-patch.json'
$utf8 = New-Object Text.UTF8Encoding($false)

$stockMapmaster = '1e076f7c5f0aea8d93ad72365bcaa267361503eee10fcdab0522c699b188508a'
$patchedMapmasterHash = 'b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f'
$stockRuiWad = '92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04'
$stockRuiDcb = '21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a'
$candidateRuiWad = 'e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959'
$candidateRuiDcb = 'b8d5627416787ae6761e0212a1e8de56e33abe7c251db838c4af20a00afc161b'

$oldStateManifests = @(
    (Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-map-visual-proof\active.json'),
    (Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-map-class-control\active.json'),
    (Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-map-class-slot\active.json')
)

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Registered Raven runtime proof is already removed.'
        return
    }
    $m = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    Restore-ProofFile $mapmaster (Join-Path $backupDir 'mapmaster.dcb') ([string]$m.mapmaster_before) ([string]$m.mapmaster_after)
    Restore-ProofFile $ruiWad (Join-Path $backupDir 'r_ui.wad') ([string]$m.rui_wad_before) ([string]$m.rui_wad_after)
    Restore-ProofFile $ruiDcb (Join-Path $backupDir 'wad_r_ui.dcb') ([string]$m.rui_dcb_before) ([string]$m.rui_dcb_after)
    Restore-ProofFile $mapmenu (Join-Path $backupDir 'mapmenu.lua') ([string]$m.mapmenu_before) ([string]$m.mapmenu_after)

    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Registered Raven runtime proof removed.'
    Write-Host 'The exact v0.10.3 native Raven baseline from before this proof was restored.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Registered Raven runtime proof is already installed.'
}
foreach ($old in $oldStateManifests) {
    if (Test-Path -LiteralPath $old -PathType Leaf) {
        throw "An older v0.10.4 Raven proof is still active: $old"
    }
}
foreach ($required in @($mapmaster,$ruiWad,$ruiDcb,$mapmenu,$boot,$candidateWad,$candidateDcb,$buildReport,$resolutionReport,$patcher,$luaBridge)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}

if ((Hash $mapmaster) -ne $stockMapmaster) {
    throw 'mapmaster.dcb is not the tested v0.10.3 native Raven baseline.'
}
if ((Hash $ruiWad) -ne $stockRuiWad -or (Hash $ruiDcb) -ne $stockRuiDcb) {
    throw 'r_ui.wad / wad_r_ui.dcb are not stock. Remove any older UI proof first.'
}
if ((Hash $candidateWad) -ne $candidateRuiWad -or (Hash $candidateDcb) -ne $candidateRuiDcb) {
    throw 'Local corrected Raven candidate hashes do not match the statically approved build.'
}

$build = Get-Content -LiteralPath $buildReport -Raw | ConvertFrom-Json
if ($build.result -ne 'OFFLINE_RAVEN_UI_REGISTERED_CLASS_CANDIDATE_BUILT' -or
    $build.gowtool_parser_validation.passed -ne $true -or
    [string]$build.candidate.r_ui_wad.sha256 -ne $candidateRuiWad -or
    [string]$build.candidate.wad_r_ui_dcb.sha256 -ne $candidateRuiDcb) {
    throw 'Corrected Raven build report is missing or does not match the approved candidate.'
}
$resolution = Get-Content -LiteralPath $resolutionReport -Raw | ConvertFrom-Json
if ($resolution.result -ne 'STATIC_RAVEN_REGISTERED_CLASS_RESOLUTION_PROVED' -or
    $resolution.static_resolution_gate_passed -ne $true -or
    $resolution.runtime_test_ready -ne $true -or
    $resolution.distinct_wad_name_hash_collision -ne $false -or
    $resolution.map_icon_parent_scope_link_count -ne 1 -or
    $resolution.gopool.raven_rows -ne 1) {
    throw 'Static Raven resolution gate is not green. Refusing runtime installation.'
}

$mapText = [IO.File]::ReadAllText($mapmenu)
if (-not $mapText.Contains('BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE')) {
    throw 'The tested v0.10.3 native Raven production bridge is not active.'
}
if ($mapText.Contains('BEGIN COMPLETIONIST V0.10.4 RAVEN REGISTERED CLASS RUNTIME PROOF')) {
    throw 'Registered Raven runtime bridge already appears in mapmenu.lua.'
}

$bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
$patches = @($bootObj.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
foreach ($entry in $patches) {
    if ([string]$entry -match '(?i)completionist_v104_raven_map|dock[_-]?raven|0Completionist_v102_dock_raven') {
        throw "A Raven/Dock texpack is still active: $entry. This class-acceptance proof intentionally loads no custom texpack."
    }
}

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
& $python.Source $patcher --input $mapmaster --output $patchedMapmaster --report $patcherReport | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Native Raven map-icon pointer patch failed.' }
if ((Hash $patchedMapmaster) -ne $patchedMapmasterHash) {
    throw 'Patched mapmaster hash differs from the previously proven deterministic output.'
}

Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backupMapmaster = Join-Path $backupDir 'mapmaster.dcb'
$backupRuiWad = Join-Path $backupDir 'r_ui.wad'
$backupRuiDcb = Join-Path $backupDir 'wad_r_ui.dcb'
$backupMapmenu = Join-Path $backupDir 'mapmenu.lua'
Copy-Item -LiteralPath $mapmaster -Destination $backupMapmaster
Copy-Item -LiteralPath $ruiWad -Destination $backupRuiWad
Copy-Item -LiteralPath $ruiDcb -Destination $backupRuiDcb
Copy-Item -LiteralPath $mapmenu -Destination $backupMapmenu

$before = [ordered]@{
    mapmaster = Hash $mapmaster
    rui_wad = Hash $ruiWad
    rui_dcb = Hash $ruiDcb
    mapmenu = Hash $mapmenu
}
foreach ($pair in @(
    @($mapmaster,$backupMapmaster),
    @($ruiWad,$backupRuiWad),
    @($ruiDcb,$backupRuiDcb),
    @($mapmenu,$backupMapmenu)
)) {
    if ((Hash $pair[0]) -ne (Hash $pair[1])) { throw "Backup hash mismatch: $($pair[0])" }
}

try {
    Copy-Item -LiteralPath $patchedMapmaster -Destination $mapmaster -Force
    Copy-Item -LiteralPath $candidateWad -Destination $ruiWad -Force
    Copy-Item -LiteralPath $candidateDcb -Destination $ruiDcb -Force
    $bridge = [IO.File]::ReadAllText($luaBridge)
    [IO.File]::WriteAllText($mapmenu, $mapText + "`r`n" + $bridge + "`r`n", $utf8)

    if ((Hash $mapmaster) -ne $patchedMapmasterHash) { throw 'Installed mapmaster hash mismatch.' }
    if ((Hash $ruiWad) -ne $candidateRuiWad) { throw 'Installed corrected r_ui.wad hash mismatch.' }
    if ((Hash $ruiDcb) -ne $candidateRuiDcb) { throw 'Installed corrected wad_r_ui.dcb hash mismatch.' }
    if (-not ([IO.File]::ReadAllText($mapmenu).Contains('BEGIN COMPLETIONIST V0.10.4 RAVEN REGISTERED CLASS RUNTIME PROOF'))) {
        throw 'Registered Raven runtime bridge missing after write.'
    }

    $after = [ordered]@{
        mapmaster = Hash $mapmaster
        rui_wad = Hash $ruiWad
        rui_dcb = Hash $ruiDcb
        mapmenu = Hash $mapmenu
    }
    $manifest = [ordered]@{
        proof = 'v0.10.4 corrected registered Raven map-class runtime acceptance'
        candidate = 'Completionist_V103_Veithurgard_Raven_01'
        map_resource = 'goMapIconCompletionistRaven'
        compass_type = 'DockPoint'
        texpack_loaded = $false
        expected_visual_at_this_gate = 'cloned stock Dock pixels; class identity is the variable under test'
        dock_proxy_used = $false
        mapmaster_before = $before.mapmaster
        mapmaster_after = $after.mapmaster
        rui_wad_before = $before.rui_wad
        rui_wad_after = $after.rui_wad
        rui_dcb_before = $before.rui_dcb
        rui_dcb_after = $after.rui_dcb
        mapmenu_before = $before.mapmenu
        mapmenu_after = $after.mapmenu
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 10) + [Environment]::NewLine, $utf8)
}
catch {
    Write-Warning "Install failed. Restoring pre-proof files: $($_.Exception.Message)"
    try {
        Copy-Item -LiteralPath $backupMapmaster -Destination $mapmaster -Force
        Copy-Item -LiteralPath $backupRuiWad -Destination $ruiWad -Force
        Copy-Item -LiteralPath $backupRuiDcb -Destination $ruiDcb -Force
        Copy-Item -LiteralPath $backupMapmenu -Destination $mapmenu -Force
    } catch {
        Write-Warning "Automatic recovery also failed: $($_.Exception.Message)"
    }
    throw
}

$reportRel = 'archive/field-logs/completionist-v104-raven-registered-runtime-install.json'
$reportPath = Join-Path $repo ($reportRel -replace '/', '\')
$installReport = [ordered]@{
    result = 'RAVEN_REGISTERED_CLASS_RUNTIME_PROOF_INSTALLED'
    installed_into_game = $true
    candidate = 'Completionist_V103_Veithurgard_Raven_01'
    map_resource = 'goMapIconCompletionistRaven'
    compass_type = 'DockPoint'
    texpack_loaded = $false
    dock_proxy_used = $false
    corrected_candidate_wad_sha256 = $candidateRuiWad
    corrected_candidate_dcb_sha256 = $candidateRuiDcb
    static_resolution_gate_passed = $true
    save_state_written = $false
    progression_state_written = $false
    native_kratos_marker_touched = $false
    reversible_manifest = $manifestPath
}
New-Item -ItemType Directory -Force -Path (Split-Path $reportPath -Parent) | Out-Null
[IO.File]::WriteAllText($reportPath, ($installReport | ConvertTo-Json -Depth 12) + [Environment]::NewLine, $utf8)

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for registered runtime install report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven registered runtime install' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for registered runtime install report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Proof installed, but pushing its install report failed.' }
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Corrected Raven registered-class runtime proof installed.'
Write-Host '- map class: goMapIconCompletionistRaven'
Write-Host '- Dock map proxy: none'
Write-Host '- custom texpack: intentionally NOT loaded at this gate'
Write-Host '- map artwork may still resemble the stock Dock because cloned stock pixels are intentional here'
Write-Host '- compass remains DockPoint temporarily'
Write-Host ''
Write-Host 'Launch God of War and open the Midgard / Veithurgard map once. If stable, close and reopen the map two or three times.'
Write-Host 'If the game crashes, do not reinstall anything; close it and run the runtime collector.'
Write-Host ("Rollback: powershell -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
