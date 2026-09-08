param(
    [ValidateSet('Install','Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Expected feat/v0.10.4-all-ravens, got '$branch'." }
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before changing the Raven resident GPU proof.' }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }

$game = [IO.Path]::GetFullPath($GameRoot)
$wad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$dcb = Join-Path $game 'exec\dc\pc_le\wad_r_ui.dcb'
$mapmaster = Join-Path $game 'exec\dc\pc_le\mapmaster.dcb'
$boot = Join-Path $game 'exec\boot-options.json'
$patcher = Join-Path $PSScriptRoot 'patch-raven-resident-gpu-donor.py'
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-resident-gpu-donor'
$manifest = Join-Path $stateDir 'active.json'
$backup = Join-Path $stateDir 'r_ui.wad.before'
$patched = Join-Path $stateDir 'r_ui.wad.valkyrie-donor'
$patchReport = Join-Path $stateDir 'patch-report.json'

$expectedWad = 'e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959'
$expectedDcb = 'b8d5627416787ae6761e0212a1e8de56e33abe7c251db838c4af20a00afc161b'
$expectedMapmaster = 'b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f'
$bindingManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-texpack-userhash-binding\active.json'
$patchLoadingManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-patch-loading\active.json'
$artManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-layer\active.json'
$utf8 = New-Object Text.UTF8Encoding($false)

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        Write-Host 'Raven resident GPU donor proof is already removed.'
        return
    }
    $m = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) { throw 'Resident GPU proof backup is missing.' }
    $current = Hash $wad
    if ($current -ne [string]$m.wad_after -and $current -ne [string]$m.wad_before) {
        throw 'r_ui.wad changed after resident GPU proof. Refusing automatic overwrite.'
    }
    Copy-Item -LiteralPath $backup -Destination $wad -Force
    if ((Hash $wad) -ne [string]$m.wad_before) { throw 'Resident GPU rollback hash mismatch.' }
    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifest -Destination $removed
    Write-Host 'Raven resident GPU donor proof removed.'
    Write-Host 'The registered Raven class, artwork layer, texpack path fix and prompt fix remain active.'
    return
}

if (Test-Path -LiteralPath $manifest -PathType Leaf) { throw 'Raven resident GPU donor proof is already installed.' }
foreach ($required in @($wad,$dcb,$mapmaster,$boot,$patcher,$bindingManifest,$patchLoadingManifest,$artManifest)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required active proof/file: $required" }
}
if ((Hash $wad) -ne $expectedWad) { throw 'r_ui.wad is not the proven registered Raven base expected by this proof.' }
if ((Hash $dcb) -ne $expectedDcb) { throw 'wad_r_ui.dcb changed from the proven registered Raven base.' }
if ((Hash $mapmaster) -ne $expectedMapmaster) { throw 'mapmaster.dcb changed from the one-Raven registered proof.' }

$bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
if (@($bootObj.'patch-texpacks') -notcontains '../../patch/pc_le/completionist_v104_raven_map') {
    throw 'Correct Raven patch texpack boot entry is not active.'
}

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
& $python.Source -m py_compile $patcher
if ($LASTEXITCODE -ne 0) { throw 'Resident GPU donor patcher syntax check failed.' }
& $python.Source $patcher --input $wad --output $patched --report $patchReport | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Resident GPU donor offline patch failed.' }

$p = Get-Content -LiteralPath $patchReport -Raw | ConvertFrom-Json
if ($p.result -ne 'RAVEN_RESIDENT_GPU_DONOR_PATCHED_OFFLINE' -or
    $p.raven_identity_preserved -ne $true -or
    $p.raven_texture_definitions_preserved -ne $true -or
    $p.external_texpack_untouched -ne $true) {
    throw 'Resident GPU donor patch report failed validation.'
}

Copy-Item -LiteralPath $wad -Destination $backup -Force
$before = Hash $wad
try {
    Copy-Item -LiteralPath $patched -Destination $wad -Force
    $after = Hash $wad
    if ($after -eq $before) { throw 'Resident GPU donor WAD did not change.' }
    if ($after -ne ([string]$p.output_wad_sha256).ToLowerInvariant()) { throw 'Installed resident GPU donor WAD hash mismatch.' }
    if ((Hash $dcb) -ne $expectedDcb -or (Hash $mapmaster) -ne $expectedMapmaster) { throw 'Unrelated registered-class files changed during install.' }

    $m = [ordered]@{
        proof = 'v0.10.4 dedicated Raven resident GPU donor control'
        donor = 'stock Valkyrie map marker resident diffuse/emissive payloads'
        map_resource = 'goMapIconCompletionistRaven'
        expected_visual = 'Valkyrie-like map marker if resident WAD GPU payload is the rendered pixel source'
        wad_before = $before
        wad_after = $after
        dcb_unchanged = $true
        mapmaster_unchanged = $true
        external_texpack_untouched = $true
        save_state_written = $false
        progression_state_written = $false
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifest, ($m | ConvertTo-Json -Depth 8) + [Environment]::NewLine, $utf8)
}
catch {
    Write-Warning "Resident GPU donor install failed. Restoring WAD: $($_.Exception.Message)"
    try { Copy-Item -LiteralPath $backup -Destination $wad -Force } catch { Write-Warning "Automatic WAD restore failed: $($_.Exception.Message)" }
    throw
}

$reportRel = 'archive/field-logs/completionist-v104-raven-resident-gpu-donor-install.json'
$reportPath = Join-Path $repo ($reportRel -replace '/', '\')
$installReport = [ordered]@{
    result = 'RAVEN_RESIDENT_GPU_DONOR_PROOF_INSTALLED'
    installed_into_game = $true
    donor = 'stock Valkyrie map marker'
    map_resource = 'goMapIconCompletionistRaven'
    wad_before = $before
    wad_after = Hash $wad
    patch = $p
    external_texpack_untouched = $true
    real_dock_resource_metadata_untouched = $true
    save_state_written = $false
    progression_state_written = $false
    reversible_manifest = $manifest
}
New-Item -ItemType Directory -Force -Path (Split-Path $reportPath -Parent) | Out-Null
[IO.File]::WriteAllText($reportPath, ($installReport | ConvertTo-Json -Depth 16) + [Environment]::NewLine, $utf8)

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for resident GPU donor install report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven resident GPU donor install' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for resident GPU donor install report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Proof installed, but pushing install report failed.' }
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Raven resident GPU donor proof installed.'
Write-Host '- only the dedicated Raven resident GPU payload bytes were changed'
Write-Host '- donor pixels: stock Valkyrie map marker'
Write-Host '- Raven class/name/texture definitions and external texpack remain unchanged'
Write-Host '- real Dock resources are not modified'
Write-Host ''
Write-Host 'Launch God of War and inspect the Raven map marker.'
Write-Host 'If it becomes Valkyrie-like, resident WAD GPU payloads are the active pixel source.'
