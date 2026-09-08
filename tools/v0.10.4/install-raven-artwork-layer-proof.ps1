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
    throw 'Close God of War before installing or removing the Raven artwork layer proof.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

function Hash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Replace-Bridge([string]$Text, [string]$Begin, [string]$End, [string]$Replacement) {
    $start = $Text.IndexOf($Begin, [StringComparison]::Ordinal)
    if ($start -lt 0) { throw "Bridge start marker missing: $Begin" }
    $finishStart = $Text.IndexOf($End, $start, [StringComparison]::Ordinal)
    if ($finishStart -lt 0) { throw "Bridge end marker missing: $End" }
    $finish = $finishStart + $End.Length
    return $Text.Substring(0, $start) + $Replacement.TrimEnd() + $Text.Substring($finish)
}

$game = [IO.Path]::GetFullPath($GameRoot)
$mapmaster = Join-Path $game 'exec\dc\pc_le\mapmaster.dcb'
$ruiWad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$ruiDcb = Join-Path $game 'exec\dc\pc_le\wad_r_ui.dcb'
$mapmenu = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$boot = Join-Path $game 'exec\boot-options.json'

$registeredManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-registered-class-runtime\active.json'
$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-layer'
$manifestPath = Join-Path $stateDir 'active.json'
$backupDir = Join-Path $stateDir 'backup'

$visualWork = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.4\raven-ui-visual-clone\texpack'
$sourcePack = Join-Path $visualWork 'completionist_v104_raven_map.texpack'
$sourceToc = Join-Path $visualWork 'completionist_v104_raven_map.texpack.toc'
$installedPack = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack'
$installedToc = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack.toc'
$patchEntry = 'completionist_v104_raven_map'

$productionLua = Join-Path (Split-Path $PSScriptRoot -Parent) 'v0.10.3\native-raven-production.lua'
$artLua = Join-Path $PSScriptRoot 'raven-artwork-layer-proof.lua'
$utf8 = New-Object Text.UTF8Encoding($false)

$expectedMapmaster = 'b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f'
$expectedRuiWad = 'e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959'
$expectedRuiDcb = 'b8d5627416787ae6761e0212a1e8de56e33abe7c251db838c4af20a00afc161b'
$expectedPack = 'a224969576eb68b004a49e2baabe7a13957f5bfe12d8fd4e0bf87e04e2dd1fc1'
$expectedToc = 'c7abce00f8a13f4dd63bad9f9c763cc54424426ecb679c60f0c496d0a95437e8'

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Raven artwork layer proof is already removed.'
        return
    }
    $m = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    foreach ($item in @(
        @{Target=$mapmenu; Backup=(Join-Path $backupDir 'mapmenu.lua'); Before=[string]$m.mapmenu_before; After=[string]$m.mapmenu_after},
        @{Target=$boot; Backup=(Join-Path $backupDir 'boot-options.json'); Before=[string]$m.boot_before; After=[string]$m.boot_after}
    )) {
        if (-not (Test-Path -LiteralPath $item.Backup -PathType Leaf)) { throw "Missing backup: $($item.Backup)" }
        $current = Hash $item.Target
        if ($current -ne $item.Before -and $current -ne $item.After) {
            throw "$($item.Target) changed after artwork-layer installation. Refusing automatic overwrite."
        }
        Copy-Item -LiteralPath $item.Backup -Destination $item.Target -Force
        if ((Hash $item.Target) -ne $item.Before) { throw "Rollback hash mismatch: $($item.Target)" }
    }
    foreach ($pair in @(@($installedPack,$expectedPack), @($installedToc,$expectedToc))) {
        if (Test-Path -LiteralPath $pair[0] -PathType Leaf) {
            if ((Hash $pair[0]) -ne $pair[1]) { throw "Installed artwork file changed: $($pair[0])" }
            Remove-Item -LiteralPath $pair[0] -Force
        }
    }
    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Raven artwork layer proof removed.'
    Write-Host 'The corrected registered-class runtime proof remains active underneath it.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Raven artwork layer proof is already installed.'
}
foreach ($required in @($registeredManifest,$mapmaster,$ruiWad,$ruiDcb,$mapmenu,$boot,$sourcePack,$sourceToc,$productionLua,$artLua)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}
if ((Hash $mapmaster) -ne $expectedMapmaster -or (Hash $ruiWad) -ne $expectedRuiWad -or (Hash $ruiDcb) -ne $expectedRuiDcb) {
    throw 'The corrected registered Raven runtime proof is not the exact active base expected by this artwork layer.'
}
if ((Hash $sourcePack) -ne $expectedPack -or (Hash $sourceToc) -ne $expectedToc) {
    throw 'Offline Raven artwork texpack hashes do not match the validated build.'
}
if ((Test-Path -LiteralPath $installedPack) -or (Test-Path -LiteralPath $installedToc)) {
    throw 'Raven artwork texpack files already exist in the game directory outside this layer state.'
}

$registered = Get-Content -LiteralPath $registeredManifest -Raw | ConvertFrom-Json
if ([string]$registered.rui_wad_after -ne $expectedRuiWad -or
    [string]$registered.rui_dcb_after -ne $expectedRuiDcb -or
    [string]$registered.mapmaster_after -ne $expectedMapmaster -or
    $registered.texpack_loaded -ne $false) {
    throw 'Active registered-runtime manifest does not match the proven class-acceptance state.'
}

$mapText = [IO.File]::ReadAllText($mapmenu)
$nativeBegin = '-- BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE'
$nativeEnd = '-- END COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE'
$artBegin = '-- BEGIN COMPLETIONIST V0.10.4 RAVEN ARTWORK LAYER PROOF'
if (-not $mapText.Contains('BEGIN COMPLETIONIST V0.10.4 RAVEN REGISTERED CLASS RUNTIME PROOF')) {
    throw 'Corrected registered-runtime Lua bridge is not active.'
}
if ($mapText.Contains($artBegin)) { throw 'Artwork-layer Lua already appears in mapmenu.lua.' }

$bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
$patches = @($bootObj.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
if ($patches -contains $patchEntry) { throw 'Raven artwork texpack is already registered in boot-options.json.' }
foreach ($entry in $patches) {
    if ([string]$entry -match '(?i)dock[_-]?raven|0Completionist_v102_dock_raven') {
        throw "Old global Dock Raven texpack is still registered: $entry"
    }
}

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backupMapmenu = Join-Path $backupDir 'mapmenu.lua'
$backupBoot = Join-Path $backupDir 'boot-options.json'
Copy-Item -LiteralPath $mapmenu -Destination $backupMapmenu -Force
Copy-Item -LiteralPath $boot -Destination $backupBoot -Force
$beforeMapmenu = Hash $mapmenu
$beforeBoot = Hash $boot

try {
    Copy-Item -LiteralPath $sourcePack -Destination $installedPack -Force
    Copy-Item -LiteralPath $sourceToc -Destination $installedToc -Force

    $bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
    $patches = @($bootObj.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
    if ($null -eq $bootObj.PSObject.Properties['patch-texpacks']) {
        $bootObj | Add-Member -NotePropertyName 'patch-texpacks' -NotePropertyValue @($patchEntry)
    } else {
        $bootObj.'patch-texpacks' = @($patches + $patchEntry)
    }
    [IO.File]::WriteAllText($boot, ($bootObj | ConvertTo-Json -Depth 30) + [Environment]::NewLine, $utf8)

    $production = [IO.File]::ReadAllText($productionLua)
    $updatedMap = Replace-Bridge $mapText $nativeBegin $nativeEnd $production
    $art = [IO.File]::ReadAllText($artLua)
    $updatedMap = $updatedMap.TrimEnd() + "`r`n" + $art.TrimEnd() + "`r`n"
    [IO.File]::WriteAllText($mapmenu, $updatedMap, $utf8)

    if ((Hash $installedPack) -ne $expectedPack -or (Hash $installedToc) -ne $expectedToc) {
        throw 'Installed Raven artwork texpack hash mismatch.'
    }
    $bootCheck = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
    if (@($bootCheck.'patch-texpacks') -notcontains $patchEntry) { throw 'Artwork patch entry missing after install.' }
    $mapCheck = [IO.File]::ReadAllText($mapmenu)
    if (-not $mapCheck.Contains($artBegin)) { throw 'Artwork diagnostic Lua missing after install.' }
    if (-not $mapCheck.Contains('prompt_async_guard=true')) { throw 'Native Raven prompt race fix was not installed.' }

    $afterMapmenu = Hash $mapmenu
    $afterBoot = Hash $boot
    $manifest = [ordered]@{
        proof = 'v0.10.4 isolated Raven artwork texpack on proven registered class'
        base_registered_runtime_active = $true
        candidate = 'Completionist_V103_Veithurgard_Raven_01'
        map_resource = 'goMapIconCompletionistRaven'
        texpack = $patchEntry
        texpack_sha256 = $expectedPack
        texpack_toc_sha256 = $expectedToc
        diagnostic_show_even_if_collected = $true
        prompt_async_guard_installed = $true
        compass_type = 'DockPoint'
        dock_proxy_used = $false
        progression_state_written = $false
        save_state_written = $false
        mapmenu_before = $beforeMapmenu
        mapmenu_after = $afterMapmenu
        boot_before = $beforeBoot
        boot_after = $afterBoot
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 10) + [Environment]::NewLine, $utf8)
}
catch {
    Write-Warning "Artwork-layer install failed. Restoring prior state: $($_.Exception.Message)"
    try {
        Copy-Item -LiteralPath $backupMapmenu -Destination $mapmenu -Force
        Copy-Item -LiteralPath $backupBoot -Destination $boot -Force
        Remove-Item -LiteralPath $installedPack,$installedToc -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Warning "Automatic recovery also failed: $($_.Exception.Message)"
    }
    throw
}

$reportRel = 'archive/field-logs/completionist-v104-raven-artwork-layer-install.json'
$reportPath = Join-Path $repo ($reportRel -replace '/', '\')
$installReport = [ordered]@{
    result = 'RAVEN_ARTWORK_LAYER_PROOF_INSTALLED'
    installed_into_game = $true
    base_registered_class_runtime = $true
    map_resource = 'goMapIconCompletionistRaven'
    texpack_loaded = $true
    texpack_sha256 = $expectedPack
    diagnostic_show_even_if_collected = $true
    prompt_async_guard_installed = $true
    compass_type = 'DockPoint'
    dock_proxy_used = $false
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
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for artwork-layer install report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven artwork layer install' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for artwork-layer report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Artwork layer installed, but report push failed.' }
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Raven artwork layer proof installed.'
Write-Host '- corrected registered class remains the map resource'
Write-Host '- custom Raven texpack is now loaded'
Write-Host '- collected Raven is rendered on the map for this visual diagnostic only'
Write-Host '- native compass remains DockPoint for now'
Write-Host '- prompt refresh race fix is active'
Write-Host '- no save/progression state was changed'
Write-Host ''
Write-Host 'Launch God of War, open Midgard/Veithurgard, and inspect the Raven map icon.'
Write-Host 'Real boat docks must remain stock. HUD compass artwork is intentionally not solved by this layer.'
