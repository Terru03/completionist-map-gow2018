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
    throw 'Close God of War before installing or removing the Raven texpack binding proof.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

function Hash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$game = [IO.Path]::GetFullPath($GameRoot)
$boot = Join-Path $game 'exec\boot-options.json'
$ruiWad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$patchPack = Join-Path $game 'exec\patch\pc_le\completionist_v104_raven_map.texpack'
$patchToc = Join-Path $game 'exec\patch\pc_le\completionist_v104_raven_map.texpack.toc'
$legacyPack = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack'
$legacyToc = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack.toc'
$patchEntry = '../../patch/pc_le/completionist_v104_raven_map'

$patchLoadingManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-patch-loading\active.json'
$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-texpack-userhash-binding'
$manifestPath = Join-Path $stateDir 'active.json'
$backupPack = Join-Path $stateDir 'before.texpack'
$backupToc = Join-Path $stateDir 'before.texpack.toc'
$workDir = Join-Path $stateDir 'work'
$patchedPack = Join-Path $workDir 'completionist_v104_raven_map.texpack'
$patchedToc = Join-Path $workDir 'completionist_v104_raven_map.texpack.toc'
$patchReport = Join-Path $workDir 'binding-report.json'
$patcher = Join-Path $PSScriptRoot 'patch-raven-texpack-userhash-binding.py'

$expectedBeforePack = 'a224969576eb68b004a49e2baabe7a13957f5bfe12d8fd4e0bf87e04e2dd1fc1'
$expectedBeforeToc = 'c7abce00f8a13f4dd63bad9f9c763cc54424426ecb679c60f0c496d0a95437e8'
$expectedWad = 'e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959'
$utf8 = New-Object Text.UTF8Encoding($false)

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Raven texpack user-hash binding proof is already removed.'
        return
    }
    $m = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    foreach ($required in @($backupPack,$backupToc,$patchPack,$patchToc)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing rollback file: $required" }
    }
    $currentPack = Hash $patchPack
    $currentToc = Hash $patchToc
    if ($currentPack -ne [string]$m.pack_after -and $currentPack -ne [string]$m.pack_before) {
        throw 'Raven patch texpack changed after binding proof installation. Refusing automatic overwrite.'
    }
    if ($currentToc -ne [string]$m.toc_after -and $currentToc -ne [string]$m.toc_before) {
        throw 'Raven patch texpack TOC changed after binding proof installation. Refusing automatic overwrite.'
    }
    Copy-Item -LiteralPath $backupPack -Destination $patchPack -Force
    Copy-Item -LiteralPath $backupToc -Destination $patchToc -Force
    if ((Hash $patchPack) -ne [string]$m.pack_before -or (Hash $patchToc) -ne [string]$m.toc_before) {
        throw 'Raven texpack binding rollback hash mismatch.'
    }
    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Raven texpack user-hash binding proof removed.'
    Write-Host 'The patch-loading fix remains active underneath it.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Raven texpack user-hash binding proof is already installed.'
}
foreach ($required in @($boot,$ruiWad,$patchPack,$patchToc,$patchLoadingManifest,$patcher)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}
if ((Hash $patchPack) -ne $expectedBeforePack -or (Hash $patchToc) -ne $expectedBeforeToc) {
    throw 'Active Raven patch texpack is not the exact pre-binding build expected by this proof.'
}
if ((Hash $ruiWad) -ne $expectedWad) {
    throw 'Active r_ui.wad is not the proven registered Raven WAD.'
}
if ((Test-Path -LiteralPath $legacyPack) -or (Test-Path -LiteralPath $legacyToc)) {
    throw 'Legacy exec\wad Raven texpack copies are present. The patch-loading migration is not in the expected state.'
}
$bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
if (@($bootObj.'patch-texpacks') -notcontains $patchEntry) {
    throw "Required Raven patch entry is missing: $patchEntry"
}
$loading = Get-Content -LiteralPath $patchLoadingManifest -Raw | ConvertFrom-Json
if ([string]$loading.texpack_sha256 -ne $expectedBeforePack -or [string]$loading.texpack_toc_sha256 -ne $expectedBeforeToc) {
    throw 'Patch-loading manifest does not match the expected Raven texpack build.'
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $pythonCmd) { throw 'python.exe is required for the offline texpack binding patch.' }

New-Item -ItemType Directory -Force -Path $stateDir,$workDir | Out-Null
Copy-Item -LiteralPath $patchPack -Destination $backupPack -Force
Copy-Item -LiteralPath $patchToc -Destination $backupToc -Force

Remove-Item -LiteralPath $patchedPack,$patchedToc,$patchReport -Force -ErrorAction SilentlyContinue
& $pythonCmd.Source $patcher `
    --pack $patchPack `
    --toc $patchToc `
    --wad $ruiWad `
    --out-pack $patchedPack `
    --out-toc $patchedToc `
    --report $patchReport
if ($LASTEXITCODE -ne 0) { throw 'Raven texpack user-hash binding patcher failed.' }
if (-not (Test-Path -LiteralPath $patchReport -PathType Leaf)) { throw 'Binding patch report was not generated.' }

$offline = Get-Content -LiteralPath $patchReport -Raw | ConvertFrom-Json
if ($offline.binding_gate_passed -ne $true) { throw 'Offline Raven texpack binding gate did not pass.' }
if ([string]$offline.input_pack_sha256 -ne $expectedBeforePack -or [string]$offline.input_toc_sha256 -ne $expectedBeforeToc) {
    throw 'Binding patcher input hashes do not match the active texpack.'
}
if ([string]$offline.wad_sha256 -ne $expectedWad) {
    throw 'Binding patcher inspected an unexpected WAD.'
}
foreach ($row in @($offline.texpack_bindings)) {
    if ([string]$row.texinfo_user_hash_after -ne [string]$row.desired_user_hash -or
        [string]$row.embedded_gnf_user_hash_after -ne [string]$row.desired_user_hash) {
        throw "Binding patch did not converge for $($row.label)."
    }
}

$afterPack = [string]$offline.output_pack_sha256
$afterToc = [string]$offline.output_toc_sha256
if ((Hash $patchedPack) -ne $afterPack -or (Hash $patchedToc) -ne $afterToc) {
    throw 'Patched Raven texpack output hashes do not match the offline report.'
}

try {
    Copy-Item -LiteralPath $patchedPack -Destination $patchPack -Force
    Copy-Item -LiteralPath $patchedToc -Destination $patchToc -Force
    if ((Hash $patchPack) -ne $afterPack -or (Hash $patchToc) -ne $afterToc) {
        throw 'Installed Raven texpack binding hashes do not match the patched outputs.'
    }

    $manifest = [ordered]@{
        proof = 'v0.10.4 Raven texpack user-hash binding proof'
        cause_under_test = 'new custom file hashes retained GOWTool default UINT64_MAX userHash while dedicated WAD expects unique custom user hashes'
        patch_entry = $patchEntry
        pack_before = $expectedBeforePack
        toc_before = $expectedBeforeToc
        pack_after = $afterPack
        toc_after = $afterToc
        wad_sha256 = $expectedWad
        bindings = @($offline.texpack_bindings)
        wad_texture_contract = $offline.wad_texture_contract
        boot_modified = $false
        wad_modified = $false
        dcb_modified = $false
        mapmaster_modified = $false
        save_state_written = $false
        progression_state_written = $false
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 20) + [Environment]::NewLine, $utf8)
}
catch {
    Write-Warning "Binding proof install failed; restoring original Raven texpack: $($_.Exception.Message)"
    try {
        Copy-Item -LiteralPath $backupPack -Destination $patchPack -Force
        Copy-Item -LiteralPath $backupToc -Destination $patchToc -Force
    } catch {
        Write-Warning "Automatic texpack recovery also failed: $($_.Exception.Message)"
    }
    throw
}

$reportRel = 'archive/field-logs/completionist-v104-raven-texpack-binding-install.json'
$reportPath = Join-Path $repo ($reportRel -replace '/', '\')
$installReport = [ordered]@{
    result = 'RAVEN_TEXPACK_USERHASH_BINDING_PROOF_INSTALLED'
    installed_into_game = $true
    binding_gate_passed = $true
    patch_entry = $patchEntry
    pack_before = $expectedBeforePack
    toc_before = $expectedBeforeToc
    pack_after = $afterPack
    toc_after = $afterToc
    wad_sha256 = $expectedWad
    texpack_bindings = @($offline.texpack_bindings)
    wad_texture_contract = $offline.wad_texture_contract
    boot_modified = $false
    wad_modified = $false
    save_state_written = $false
    progression_state_written = $false
    reversible_manifest = $manifestPath
}
New-Item -ItemType Directory -Force -Path (Split-Path $reportPath -Parent) | Out-Null
[IO.File]::WriteAllText($reportPath, ($installReport | ConvertTo-Json -Depth 20) + [Environment]::NewLine, $utf8)

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for Raven texpack binding install report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven texpack binding install' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for Raven texpack binding report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Binding proof installed, but report push failed.' }
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Raven texpack user-hash binding proof installed.'
Write-Host '- dedicated Raven WAD/DCB/map resource are unchanged'
Write-Host '- only the Raven patch texpack metadata + embedded GNF user hashes changed'
Write-Host '- real Dock resources are untouched'
Write-Host '- prompt fix and native navigation are unchanged'
Write-Host '- saves/progression are untouched'
Write-Host ''
Write-Host 'Launch God of War and inspect the Raven map marker again.'
