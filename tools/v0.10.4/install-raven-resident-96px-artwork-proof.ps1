param(
    [ValidateSet('Install','Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Expected feat/v0.10.4-all-ravens, got '$branch'." }
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before changing the Raven resident artwork proof.' }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }

$game = [IO.Path]::GetFullPath($GameRoot)
$wad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$dcb = Join-Path $game 'exec\dc\pc_le\wad_r_ui.dcb'
$mapmaster = Join-Path $game 'exec\dc\pc_le\mapmaster.dcb'
$boot = Join-Path $game 'exec\boot-options.json'
$patcher = Join-Path $PSScriptRoot 'patch-raven-resident-artwork-v3.py'
$ravenPng = Join-Path $repo 'assets\icons\concepts\raven_concept_master.png'
$texconv = Join-Path $env:LOCALAPPDATA 'CompletionistMap\tools\DirectXTex-may2026\texconv.exe'
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$expectedWad = 'e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959'
$expectedDcb = 'b8d5627416787ae6761e0212a1e8de56e33abe7c251db838c4af20a00afc161b'
$expectedMapmaster = 'b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f'
$expectedTexconv = 'dcfdec10244e02cf5037fba089c55fb7e1326b1c8181742d77d15fa5cb5eef06'

$bindingManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-texpack-userhash-binding\active.json'
$patchLoadingManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-patch-loading\active.json'
$artManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-layer\active.json'
$donorManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-resident-gpu-donor\active.json'

$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-resident-96px-artwork'
$manifest = Join-Path $stateDir 'active.json'
$backup = Join-Path $stateDir 'r_ui.wad.before'
$patched = Join-Path $stateDir 'r_ui.wad.raven-resident-96px'
$patchReport = Join-Path $stateDir 'patch-report.json'
$utf8 = New-Object Text.UTF8Encoding($false)

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        Write-Host 'Raven resident 96px artwork proof is already removed.'
        return
    }
    $m = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) { throw 'Resident 96px artwork backup is missing.' }
    $current = Hash $wad
    if ($current -ne [string]$m.wad_after -and $current -ne [string]$m.wad_before) {
        throw 'r_ui.wad changed after resident 96px artwork proof. Refusing automatic overwrite.'
    }
    Copy-Item -LiteralPath $backup -Destination $wad -Force
    if ((Hash $wad) -ne [string]$m.wad_before) { throw 'Resident 96px artwork rollback hash mismatch.' }
    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifest -Destination $removed
    Write-Host 'Raven resident 96px artwork proof removed.'
    Write-Host 'The registered Raven class, prompt fix, artwork layer and external Raven texpack remain active.'
    return
}

if (Test-Path -LiteralPath $manifest -PathType Leaf) { throw 'Raven resident 96px artwork proof is already installed.' }
if (Test-Path -LiteralPath $donorManifest -PathType Leaf) {
    throw 'The Valkyrie resident GPU donor proof is still active. Remove it first.'
}
foreach ($required in @($wad,$dcb,$mapmaster,$boot,$patcher,$ravenPng,$texconv,$bindingManifest,$patchLoadingManifest,$artManifest)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required active proof/file: $required" }
}
if ((Hash $wad) -ne $expectedWad) { throw 'r_ui.wad is not the proven registered Raven base.' }
if ((Hash $dcb) -ne $expectedDcb) { throw 'wad_r_ui.dcb changed from the proven registered Raven base.' }
if ((Hash $mapmaster) -ne $expectedMapmaster) { throw 'mapmaster.dcb changed from the one-Raven registered proof.' }
if ((Hash $texconv) -ne $expectedTexconv) { throw 'texconv hash does not match the pinned May 2026 build.' }

$bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
if (@($bootObj.'patch-texpacks') -notcontains '../../patch/pc_le/completionist_v104_raven_map') {
    throw 'Correct Raven patch texpack boot entry is not active.'
}

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
& $python.Source -m py_compile $patcher
if ($LASTEXITCODE -ne 0) { throw 'Resident 96px artwork patcher syntax check failed.' }

& $python.Source $patcher `
    --wad $wad `
    --raven-png $ravenPng `
    --texconv $texconv `
    --output $patched `
    --report $patchReport | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Resident Raven 96px artwork offline patch failed.' }

$p = Get-Content -LiteralPath $patchReport -Raw | ConvertFrom-Json
if ($p.result -ne 'RAVEN_RESIDENT_96PX_ARTWORK_PATCHED_OFFLINE' -or
    $p.resident_96px_layout_gate_passed -ne $true -or
    $p.raven_dock_resident_prefix_preserved -ne $true -or
    $p.stock_resident_prefix_is_not_universal -ne $true -or
    $p.custom_raven_96px_swizzle_applied -ne $true -or
    $p.raven_texture_definitions_preserved -ne $true -or
    $p.raven_resource_identity_preserved -ne $true -or
    $p.real_dock_and_valkyrie_records_untouched -ne $true) {
    throw 'Resident Raven 96px static proof failed. Nothing was installed.'
}

Copy-Item -LiteralPath $wad -Destination $backup -Force
$before = Hash $wad
try {
    Copy-Item -LiteralPath $patched -Destination $wad -Force
    $after = Hash $wad
    if ($after -eq $before) { throw 'Resident 96px artwork WAD did not change.' }
    if ($after -ne ([string]$p.output_wad_sha256).ToLowerInvariant()) { throw 'Installed resident 96px artwork WAD hash mismatch.' }
    if ((Hash $dcb) -ne $expectedDcb -or (Hash $mapmaster) -ne $expectedMapmaster) {
        throw 'Unrelated registered-class files changed during install.'
    }

    $m = [ordered]@{
        proof = 'v0.10.4 dedicated Raven custom 96px resident artwork'
        map_resource = 'goMapIconCompletionistRaven'
        resident_layout = 'preserve Raven Dock-derived 12-byte resident prefix + standalone 96x96 BC swizzled body'
        diffuse_layout = '9228 = 12 + 96*96*8/8'
        emissive_layout = '4620 = 12 + 96*96*4/8'
        resident_prefix_scope = 'resource-specific; Raven prefix preserved from its Dock-derived baseline'
        wad_before = $before
        wad_after = $after
        dcb_unchanged = $true
        mapmaster_unchanged = $true
        real_dock_valkyrie_untouched = $true
        save_state_written = $false
        progression_state_written = $false
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifest, ($m | ConvertTo-Json -Depth 8) + [Environment]::NewLine, $utf8)
}
catch {
    Write-Warning "Resident 96px artwork install failed. Restoring WAD: $($_.Exception.Message)"
    try { Copy-Item -LiteralPath $backup -Destination $wad -Force } catch { Write-Warning "Automatic WAD restore failed: $($_.Exception.Message)" }
    throw
}

$reportRel = 'archive/field-logs/completionist-v104-raven-resident-96px-artwork-install.json'
$reportPath = Join-Path $repo ($reportRel -replace '/', '\')
$installReport = [ordered]@{
    result = 'RAVEN_RESIDENT_96PX_ARTWORK_PROOF_INSTALLED'
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
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for resident 96px artwork install report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven resident 96px artwork install' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for resident 96px artwork report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Proof installed, but pushing install report failed.' }
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Raven resident 96px artwork proof installed.'
Write-Host '- the failed mip-tail assumption is no longer used'
Write-Host '- resident body is generated as a standalone 96x96 BC surface'
Write-Host '- the Raven/Dock-derived resident prefix is preserved exactly; Valkyrie is allowed to use a different prefix'
Write-Host '- only the isolated Raven resident payloads were changed'
Write-Host '- real Dock and Valkyrie resources remain untouched'
Write-Host '- HUD compass remains DockPoint for now'
Write-Host ''
Write-Host 'Launch God of War and inspect the Raven MAP marker. Expected: custom Raven artwork.'
