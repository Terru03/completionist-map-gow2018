param(
    [ValidateSet('Install','Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Expected feat/v0.10.4-all-ravens, got '$branch'." }
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before changing the Raven resident partial-linearization proof.' }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }

$game = [IO.Path]::GetFullPath($GameRoot)
$wad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$dcb = Join-Path $game 'exec\dc\pc_le\wad_r_ui.dcb'
$mapmaster = Join-Path $game 'exec\dc\pc_le\mapmaster.dcb'
$boot = Join-Path $game 'exec\boot-options.json'
$rootPack = Join-Path $game 'exec\wad\pc_le\root.texpack'
$ravenPack = Join-Path $game 'exec\patch\pc_le\completionist_v104_raven_map.texpack'
$patcher = Join-Path $PSScriptRoot 'patch-raven-resident-partial-linearization.py'
$python = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $python) { throw 'Python 3.9+ required.' }

$expectedWad = 'e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959'
$expectedDcb = 'b8d5627416787ae6761e0212a1e8de56e33abe7c251db838c4af20a00afc161b'
$expectedMapmaster = 'b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f'
$expectedPack = '648a16a6fabd526b56c1be8d18c5f983b5257296e28081c81edafb8790a1c6a7'

$bindingManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-texpack-userhash-binding\active.json'
$patchLoadingManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-patch-loading\active.json'
$artManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-layer\active.json'
$old96Manifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-resident-96px-artwork\active.json'
$donorManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-resident-gpu-donor\active.json'

$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-resident-partial-linearization'
$manifest = Join-Path $stateDir 'active.json'
$backup = Join-Path $stateDir 'r_ui.wad.before'
$runId = [Guid]::NewGuid().ToString('N')
$patched = Join-Path $stateDir ('r_ui.wad.' + $runId)
$patchReport = Join-Path $stateDir ('patch-report-' + $runId + '.json')
$utf8 = New-Object Text.UTF8Encoding($false)

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        Write-Information -InformationAction Continue 'Raven resident partial-linearization proof is already removed.'
        return
    }
    $m = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) { throw 'Resident partial-linearization backup is missing.' }
    if ((Hash $backup) -ne $expectedWad -or [string]$m.wad_before -ne $expectedWad) { throw 'Backup is not clean registered-Raven base.' }
    if ([string]$m.game_root -ne $game) { throw 'Proof belongs to different game root.' }
    $current = Hash $wad
    if ($current -ne [string]$m.wad_after -and $current -ne [string]$m.wad_before) {
        throw 'r_ui.wad changed after resident partial-linearization proof. Refusing automatic overwrite.'
    }
    Copy-Item -LiteralPath $backup -Destination $wad -Force
    if ((Hash $wad) -ne [string]$m.wad_before) { throw 'Resident partial-linearization rollback hash mismatch.' }
    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifest -Destination $removed
    Write-Information -InformationAction Continue 'Raven resident partial-linearization proof removed.'
    Write-Information -InformationAction Continue 'The registered Raven class, prompt fix, artwork layer and external Raven texpack remain active.'
    return
}

if (Test-Path -LiteralPath $manifest -PathType Leaf) { throw 'Raven resident partial-linearization proof already active.' }
$stateRoot = Split-Path $stateDir -Parent
foreach ($dir in @(Get-ChildItem -LiteralPath $stateRoot -Directory -ErrorAction Stop)) {
    if ($dir.Name -like '*resident*' -and (Test-Path -LiteralPath (Join-Path $dir.FullName 'active.json'))) {
        throw "Resident proof active: $($dir.Name). Remove it first."
    }
}
if (Test-Path -LiteralPath $old96Manifest -PathType Leaf) {
    throw 'The corrupt 96px resident proof is still active. Remove it first with install-raven-resident-96px-artwork-proof.ps1 -Mode Remove.'
}
if (Test-Path -LiteralPath $donorManifest -PathType Leaf) {
    throw 'The Valkyrie resident GPU donor proof is still active. Remove it first.'
}
foreach ($required in @($wad,$dcb,$mapmaster,$boot,$rootPack,$ravenPack,$patcher,$bindingManifest,$patchLoadingManifest,$artManifest)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required active proof/file: $required" }
}
if ((Hash $wad) -ne $expectedWad) { throw 'r_ui.wad is not the proven registered Raven base. Remove any resident artwork proof first.' }
if ((Hash $dcb) -ne $expectedDcb) { throw 'wad_r_ui.dcb changed from the proven registered Raven base.' }
if ((Hash $mapmaster) -ne $expectedMapmaster) { throw 'mapmaster.dcb changed from the one-Raven registered proof.' }
if ((Hash $ravenPack) -ne $expectedPack) { throw 'Active Raven texpack is not the user-hash-bound build expected by this proof.' }

$bootBefore = Hash $boot
$bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
if (@($bootObj.'patch-texpacks') -notcontains '../../patch/pc_le/completionist_v104_raven_map') {
    throw 'Correct Raven patch texpack boot entry is not active.'
}

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
& $python.Source -m py_compile $patcher
if ($LASTEXITCODE -ne 0) { throw 'Resident partial-linearization patcher syntax check failed.' }

& $python.Source $patcher `
    --wad $wad `
    --dcb $dcb `
    --mapmaster $mapmaster `
    --root-texpack $rootPack `
    --raven-texpack $ravenPack `
    --output $patched `
    --report $patchReport | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Resident Raven partial-linearization offline patch failed.' }

$p = Get-Content -LiteralPath $patchReport -Raw | ConvertFrom-Json
if ($p.result -ne 'RAVEN_RESIDENT_PARTIAL_LINEARIZATION_PATCHED_OFFLINE' -or
    $p.all_four_stock_resources_reconstructed_exactly -ne $true -or
    $p.runtime_patch_gate -ne $true -or
    $p.input_wad_sha256 -ne $expectedWad -or
    $p.dcb_sha256 -ne $expectedDcb -or
    $p.mapmaster_sha256 -ne $expectedMapmaster -or
    $p.raven_texpack_sha256 -ne $expectedPack -or
    $p.only_two_raven_gpu_payloads_changed -ne $true -or
    $p.output_round_trip_exact -ne $true -or
    $p.trailing_12_bytes_preserved -ne $true -or
    $p.raven_texture_definitions_preserved -ne $true -or
    $p.raven_resource_identity_preserved -ne $true -or
    $p.real_dock_and_valkyrie_records_untouched -ne $true) {
    throw 'Resident Raven partial-linearization static proof failed. Nothing was installed.'
}

if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before install.' }
if ((Hash $wad) -ne $expectedWad -or (Hash $dcb) -ne $expectedDcb -or
    (Hash $mapmaster) -ne $expectedMapmaster -or (Hash $ravenPack) -ne $expectedPack) {
    throw 'Inputs changed during offline proof.'
}
if ((Hash $patched) -ne [string]$p.output_wad_sha256) { throw 'Offline output hash changed.' }
if ((Hash $boot) -ne $bootBefore -or (Hash $rootPack) -ne [string]$p.root_texpack_sha256) { throw 'Boot or stock texpack changed during proof.' }
foreach ($dir in @(Get-ChildItem -LiteralPath $stateRoot -Directory)) {
    if ($dir.Name -like '*resident*' -and (Test-Path -LiteralPath (Join-Path $dir.FullName 'active.json'))) { throw 'Resident proof became active during build.' }
}
Copy-Item -LiteralPath $wad -Destination $backup -Force
if ((Hash $backup) -ne $expectedWad) { throw 'Backup hash mismatch. Nothing installed.' }
$before = Hash $wad
try {
    Copy-Item -LiteralPath $patched -Destination $wad -Force
    $after = Hash $wad
    if ($after -eq $before) { throw 'Resident partial-linearization WAD did not change.' }
    if ($after -ne ([string]$p.output_wad_sha256).ToLowerInvariant()) { throw 'Installed resident partial-linearization WAD hash mismatch.' }
    if ((Hash $boot) -ne $bootBefore -or (Hash $dcb) -ne $expectedDcb -or (Hash $mapmaster) -ne $expectedMapmaster -or (Hash $ravenPack) -ne $expectedPack) {
        throw 'Unrelated registered-class/texpack files changed during install.'
    }

    $m = [ordered]@{
        proof = 'v0.10.4 dedicated Raven resident partial-linearization artwork'
        map_resource = 'goMapIconCompletionistRaven'
        resident_layout = 'mip2..7: unswizzle, pack active rows, retain raw tail; preserve final 12 bytes'
        all_four_stock_resources_reconstructed_exactly = $true
        runtime_patch_gate = $true
        game_root = $game
        patch_report = $patchReport
        external_texpack = '../../patch/pc_le/completionist_v104_raven_map'
        wad_before = $before
        wad_after = $after
        dcb_unchanged = $true
        mapmaster_unchanged = $true
        external_texpack_unchanged = $true
        real_dock_valkyrie_untouched = $true
        save_state_written = $false
        progression_state_written = $false
        marker_state_written = $false
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifest, ($m | ConvertTo-Json -Depth 8) + [Environment]::NewLine, $utf8)
    $reportRel = 'archive/field-logs/completionist-v104-raven-resident-partial-linearization-install.json'
    $reportPath = Join-Path $repo ($reportRel -replace '/', '\')
    $installReport = [ordered]@{
        result = 'RAVEN_RESIDENT_PARTIAL_LINEARIZATION_PROOF_INSTALLED'
        installed_into_game = $true
        map_resource = 'goMapIconCompletionistRaven'
        wad_before = $before
        wad_after = Hash $wad
        patch = $p
        real_dock_valkyrie_resources_untouched = $true
        hud_compass_type = 'DockPoint unchanged for this proof'
        save_state_written = $false
        progression_state_written = $false
        reversible_manifest = $manifest
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $reportPath -Parent) | Out-Null
    [IO.File]::WriteAllText($reportPath, ($installReport | ConvertTo-Json -Depth 24) + [Environment]::NewLine, $utf8)

    Push-Location $repo
    try {
        git add -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git add failed for resident partial-linearization install report.' }
        git diff --cached --check -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
        git diff --cached --quiet -- $reportRel
        if ($LASTEXITCODE -ne 0) {
            git commit -m 'Archive Raven resident partial-linearization install' -- $reportRel
            if ($LASTEXITCODE -ne 0) { throw 'git commit failed for resident partial-linearization artwork report.' }

        }
    }
    finally { Pop-Location }
    git -C $repo push $Remote $branch
    if ($LASTEXITCODE -ne 0) { throw 'Install report push failed.' }
}
catch {
    $installError = $_
    Write-Warning "Install failed. Restore WAD: $($installError.Exception.Message)"
    if ((Hash $backup) -ne $expectedWad) { throw 'Rollback refused: backup hash changed.' }
    Copy-Item -LiteralPath $backup -Destination $wad -Force
    if ((Hash $wad) -ne $expectedWad) { throw 'Rollback WAD hash mismatch.' }
    if (Test-Path -LiteralPath $manifest) {
        Move-Item -LiteralPath $manifest -Destination (Join-Path $stateDir ('failed-' + $runId + '.json'))
    }
    if ($reportPath -and (Test-Path -LiteralPath $reportPath)) {
        $failedReport = [ordered]@{ result = 'RAVEN_RESIDENT_PARTIAL_LINEARIZATION_INSTALL_ROLLED_BACK'; installed_into_game = $false; wad_after = Hash $wad; error = $installError.Exception.Message }
        [IO.File]::WriteAllText($reportPath, ($failedReport | ConvertTo-Json) + [Environment]::NewLine, $utf8)
        # Keep index and history in sync with restored WAD.
        git -C $repo add -- $reportRel
        if ($LASTEXITCODE -eq 0) {
            git -C $repo diff --cached --check -- $reportRel
            if ($LASTEXITCODE -eq 0) {
                git -C $repo commit -m 'Archive Raven partial-linearization rollback' -- $reportRel
                if ($LASTEXITCODE -eq 0) {
                    git -C $repo push $Remote $branch
                    if ($LASTEXITCODE -ne 0) { Write-Warning 'Rollback report committed. Push still failed.' }
                } else { Write-Warning 'Rollback report staged. Commit failed; resolve before push.' }
            } else { Write-Warning 'Rollback report static check failed; resolve before push.' }
        } else { Write-Warning 'Rollback report could not be staged; resolve before push.' }
    }
    throw $installError
}

Write-Information -InformationAction Continue 'Raven partial-linearization proof installed. Four stock checks byte-exact.'
Write-Information -InformationAction Continue 'Map should show custom Raven. HUD compass stays DockPoint. Test map in game.'
