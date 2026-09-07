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
    throw 'Close God of War before installing or removing the Raven map visual proof.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

function Hash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$game = [IO.Path]::GetFullPath($GameRoot)
$mapmaster = Join-Path $game 'exec\dc\pc_le\mapmaster.dcb'
$ruiDcb = Join-Path $game 'exec\dc\pc_le\wad_r_ui.dcb'
$ruiWad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$boot = Join-Path $game 'exec\boot-options.json'
$mapmenu = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'

$visualWork = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.4\raven-ui-visual-clone'
$candidateWad = Join-Path $visualWork 'r_ui.wad'
$candidateDcb = Join-Path $visualWork 'wad_r_ui.dcb'
$candidatePack = Join-Path $visualWork 'texpack\completionist_v104_raven_map.texpack'
$candidateToc = Join-Path $visualWork 'texpack\completionist_v104_raven_map.texpack.toc'

$installedPack = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack'
$installedToc = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack.toc'
$patchEntry = 'completionist_v104_raven_map'

$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-map-visual-proof'
$manifestPath = Join-Path $stateDir 'active.json'
$backupDir = Join-Path $stateDir 'backup'
$patchedMapmaster = Join-Path $stateDir 'mapmaster-raven-visual.dcb'
$patcherReport = Join-Path $stateDir 'mapmaster-patch.json'
$patcher = Join-Path $PSScriptRoot 'patch-native-raven-map-icon.py'
$luaBridge = Join-Path $PSScriptRoot 'raven-map-visual-proof.lua'
$utf8 = New-Object Text.UTF8Encoding($false)

$stockRuiWad = '92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04'
$stockRuiDcb = '21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a'
$candidateRuiWad = 'd33d623df5ea7589d78a48f8ba70d09d46ce2f2edaa0ff0f87d5e5a61e6c4425'
$candidateRuiDcb = 'b8d5627416787ae6761e0212a1e8de56e33abe7c251db838c4af20a00afc161b'
$candidatePackHash = 'a224969576eb68b004a49e2baabe7a13957f5bfe12d8fd4e0bf87e04e2dd1fc1'
$candidateTocHash = 'c7abce00f8a13f4dd63bad9f9c763cc54424426ecb679c60f0c496d0a95437e8'

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

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Raven map visual proof is already removed.'
        return
    }
    $m = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    Restore-ProofFile $mapmaster (Join-Path $backupDir 'mapmaster.dcb') ([string]$m.mapmaster_before) ([string]$m.mapmaster_after)
    Restore-ProofFile $ruiWad (Join-Path $backupDir 'r_ui.wad') ([string]$m.rui_wad_before) ([string]$m.rui_wad_after)
    Restore-ProofFile $ruiDcb (Join-Path $backupDir 'wad_r_ui.dcb') ([string]$m.rui_dcb_before) ([string]$m.rui_dcb_after)
    Restore-ProofFile $mapmenu (Join-Path $backupDir 'mapmenu.lua') ([string]$m.mapmenu_before) ([string]$m.mapmenu_after)

    if (-not (Test-Path -LiteralPath (Join-Path $backupDir 'boot-options.json') -PathType Leaf)) {
        throw 'Missing boot-options backup.'
    }
    Copy-Item -LiteralPath (Join-Path $backupDir 'boot-options.json') -Destination $boot -Force
    Remove-Item -LiteralPath $installedPack, $installedToc -Force -ErrorAction SilentlyContinue

    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Raven map visual proof removed.'
    Write-Host 'v0.10.3 native Raven state from immediately before this proof was restored exactly.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Raven map visual proof is already installed.'
}
foreach ($required in @($mapmaster,$ruiDcb,$ruiWad,$boot,$mapmenu,$candidateWad,$candidateDcb,$candidatePack,$candidateToc,$patcher,$luaBridge)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}
if ((Hash $ruiWad) -ne $stockRuiWad -or (Hash $ruiDcb) -ne $stockRuiDcb) {
    throw 'r_ui.wad / wad_r_ui.dcb are not stock. Remove any older UI/WAD proof before this test.'
}
if ((Hash $candidateWad) -ne $candidateRuiWad -or (Hash $candidateDcb) -ne $candidateRuiDcb -or
    (Hash $candidatePack) -ne $candidatePackHash -or (Hash $candidateToc) -ne $candidateTocHash) {
    throw 'Offline Raven visual candidate hashes do not match the validated build report.'
}

$mapText = [IO.File]::ReadAllText($mapmenu)
if (-not $mapText.Contains('BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE')) {
    throw 'The tested v0.10.3 native Raven production candidate is not active. Restore/install it before this visual proof.'
}
if ($mapText.Contains('BEGIN COMPLETIONIST V0.10.4 RAVEN MAP VISUAL PROOF')) {
    throw 'The v0.10.4 Raven map visual bridge is already present in mapmenu.lua.'
}

$bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
$existingPatches = @($bootObj.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
foreach ($entry in $existingPatches) {
    if ([string]$entry -match '(?i)dock[_-]?raven|0Completionist_v102_dock_raven|completionist_v102_dock_raven') {
        throw "Old global Dock Raven texpack is still registered: $entry. Run tools\v0.10.4\remove-global-dock-raven-proof.ps1 first."
    }
}
if ($existingPatches -contains $patchEntry -or (Test-Path -LiteralPath $installedPack) -or (Test-Path -LiteralPath $installedToc)) {
    throw 'v0.10.4 Raven map texpack already appears installed outside this proof state.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
& $python.Source $patcher --input $mapmaster --output $patchedMapmaster --report $patcherReport | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Native Raven map-icon pointer patch failed.' }
if (-not (Test-Path -LiteralPath $patchedMapmaster -PathType Leaf)) { throw 'Patched mapmaster was not produced.' }

Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$before = [ordered]@{
    mapmaster = Hash $mapmaster
    rui_wad = Hash $ruiWad
    rui_dcb = Hash $ruiDcb
    mapmenu = Hash $mapmenu
    boot = Hash $boot
}
Copy-Item -LiteralPath $mapmaster -Destination (Join-Path $backupDir 'mapmaster.dcb')
Copy-Item -LiteralPath $ruiWad -Destination (Join-Path $backupDir 'r_ui.wad')
Copy-Item -LiteralPath $ruiDcb -Destination (Join-Path $backupDir 'wad_r_ui.dcb')
Copy-Item -LiteralPath $mapmenu -Destination (Join-Path $backupDir 'mapmenu.lua')
Copy-Item -LiteralPath $boot -Destination (Join-Path $backupDir 'boot-options.json')
foreach ($pair in @(
    @($mapmaster,(Join-Path $backupDir 'mapmaster.dcb')),
    @($ruiWad,(Join-Path $backupDir 'r_ui.wad')),
    @($ruiDcb,(Join-Path $backupDir 'wad_r_ui.dcb')),
    @($mapmenu,(Join-Path $backupDir 'mapmenu.lua')),
    @($boot,(Join-Path $backupDir 'boot-options.json'))
)) {
    if ((Hash $pair[0]) -ne (Hash $pair[1])) { throw "Backup hash mismatch: $($pair[0])" }
}

try {
    Copy-Item -LiteralPath $patchedMapmaster -Destination $mapmaster -Force
    Copy-Item -LiteralPath $candidateWad -Destination $ruiWad -Force
    Copy-Item -LiteralPath $candidateDcb -Destination $ruiDcb -Force
    Copy-Item -LiteralPath $candidatePack -Destination $installedPack -Force
    Copy-Item -LiteralPath $candidateToc -Destination $installedToc -Force

    $bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
    $patches = @($bootObj.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
    if ($patches -notcontains $patchEntry) {
        if ($null -eq $bootObj.PSObject.Properties['patch-texpacks']) {
            $bootObj | Add-Member -NotePropertyName 'patch-texpacks' -NotePropertyValue @($patchEntry)
        } else {
            $bootObj.'patch-texpacks' = @($patches + $patchEntry)
        }
    }
    [IO.File]::WriteAllText($boot, ($bootObj | ConvertTo-Json -Depth 30) + [Environment]::NewLine, $utf8)

    $bridge = [IO.File]::ReadAllText($luaBridge)
    [IO.File]::WriteAllText($mapmenu, $mapText + "`r`n" + $bridge + "`r`n", $utf8)

    if ((Hash $ruiWad) -ne $candidateRuiWad) { throw 'Installed r_ui.wad hash mismatch.' }
    if ((Hash $ruiDcb) -ne $candidateRuiDcb) { throw 'Installed wad_r_ui.dcb hash mismatch.' }
    if ((Hash $installedPack) -ne $candidatePackHash -or (Hash $installedToc) -ne $candidateTocHash) { throw 'Installed texpack hash mismatch.' }
    $bootCheck = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
    if (@($bootCheck.'patch-texpacks') -notcontains $patchEntry) { throw 'Raven map texpack boot entry missing after write.' }
    if (-not ([IO.File]::ReadAllText($mapmenu).Contains('BEGIN COMPLETIONIST V0.10.4 RAVEN MAP VISUAL PROOF'))) { throw 'Raven map visual Lua bridge missing after write.' }

    $after = [ordered]@{
        mapmaster = Hash $mapmaster
        rui_wad = Hash $ruiWad
        rui_dcb = Hash $ruiDcb
        mapmenu = Hash $mapmenu
        boot = Hash $boot
    }
    $manifest = [ordered]@{
        proof = 'v0.10.4 Raven-only map visual isolation'
        mapmaster_before = $before.mapmaster
        mapmaster_after = $after.mapmaster
        rui_wad_before = $before.rui_wad
        rui_wad_after = $after.rui_wad
        rui_dcb_before = $before.rui_dcb
        rui_dcb_after = $after.rui_dcb
        mapmenu_before = $before.mapmenu
        mapmenu_after = $after.mapmenu
        boot_before = $before.boot
        boot_after = $after.boot
        texpack = $patchEntry
        candidate = 'Completionist_V103_Veithurgard_Raven_01'
        map_resource = 'goMapIconCompletionistRaven'
        compass_type = 'DockPoint'
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8) + [Environment]::NewLine, $utf8)
}
catch {
    Write-Warning "Install failed. Restoring pre-proof files: $($_.Exception.Message)"
    try {
        Copy-Item -LiteralPath (Join-Path $backupDir 'mapmaster.dcb') -Destination $mapmaster -Force
        Copy-Item -LiteralPath (Join-Path $backupDir 'r_ui.wad') -Destination $ruiWad -Force
        Copy-Item -LiteralPath (Join-Path $backupDir 'wad_r_ui.dcb') -Destination $ruiDcb -Force
        Copy-Item -LiteralPath (Join-Path $backupDir 'mapmenu.lua') -Destination $mapmenu -Force
        Copy-Item -LiteralPath (Join-Path $backupDir 'boot-options.json') -Destination $boot -Force
        Remove-Item -LiteralPath $installedPack,$installedToc -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Warning "Automatic recovery also failed: $($_.Exception.Message)"
    }
    throw
}

$reportRel = 'archive/field-logs/completionist-v104-raven-map-visual-proof-install.json'
$reportPath = Join-Path $repo ($reportRel -replace '/', '\')
$installReport = [ordered]@{
    result = 'RAVEN_MAP_VISUAL_PROOF_INSTALLED'
    installed_into_game = $true
    save_state_written = $false
    progression_state_written = $false
    dedicated_map_resource = 'goMapIconCompletionistRaven'
    native_compass_type = 'DockPoint'
    stock_dock_texture_hashes_overwritten = $false
    native_kratos_marker_touched = $false
    reversible_manifest = $manifestPath
    mapmaster_patch = (Get-Content -LiteralPath $patcherReport -Raw | ConvertFrom-Json)
    files = [ordered]@{
        mapmaster_before = $before.mapmaster; mapmaster_after = $after.mapmaster
        rui_wad_before = $before.rui_wad; rui_wad_after = $after.rui_wad
        rui_dcb_before = $before.rui_dcb; rui_dcb_after = $after.rui_dcb
        texpack_sha256 = Hash $installedPack
        texpack_toc_sha256 = Hash $installedToc
    }
}
New-Item -ItemType Directory -Force -Path (Split-Path $reportPath -Parent) | Out-Null
[IO.File]::WriteAllText($reportPath, ($installReport | ConvertTo-Json -Depth 20) + [Environment]::NewLine, $utf8)

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for visual proof install report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven map visual proof install' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for visual proof install report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Proof installed successfully, but pushing its report failed.' }
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Raven-only map visual proof installed.'
Write-Host '- map icon resource: goMapIconCompletionistRaven'
Write-Host '- Raven textures are unique; stock Dock textures were not overwritten'
Write-Host '- native compass navigation remains DockPoint'
Write-Host '- Kratos/Omega untouched'
Write-Host ''
Write-Host 'Launch God of War and open the Midgard map at the remaining Veithurgard Raven.'
Write-Host 'Expected: Completionist Raven shows Raven artwork; real Dock markers keep stock Dock artwork.'
Write-Host ("Rollback: powershell -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
