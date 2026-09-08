param(
    [ValidateSet('Install','Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') {
    throw "Expected feat/v0.10.4-all-ravens, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before changing Raven artwork patch loading.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

function Hash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$game = [IO.Path]::GetFullPath($GameRoot)
$boot = Join-Path $game 'exec\boot-options.json'
$artManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-layer\active.json'
$stateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-patch-loading'
$manifestPath = Join-Path $stateDir 'active.json'
$backupBoot = Join-Path $stateDir 'boot-options.json.before'

$sourceDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.4\raven-ui-visual-clone\texpack'
$sourcePack = Join-Path $sourceDir 'completionist_v104_raven_map.texpack'
$sourceToc = Join-Path $sourceDir 'completionist_v104_raven_map.texpack.toc'

# The first artwork-layer installer put the texpack beside r_ui.wad and used a
# bare boot entry. The previously field-proven v0.10.2 texpack route instead
# loads patch texpacks from exec\patch\pc_le using an exec-relative path.
$legacyPack = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack'
$legacyToc = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack.toc'
$legacyEntry = 'completionist_v104_raven_map'

$patchDir = Join-Path $game 'exec\patch\pc_le'
$patchPack = Join-Path $patchDir 'completionist_v104_raven_map.texpack'
$patchToc = Join-Path $patchDir 'completionist_v104_raven_map.texpack.toc'
$patchEntry = '../../patch/pc_le/completionist_v104_raven_map'

$expectedPack = 'a224969576eb68b004a49e2baabe7a13957f5bfe12d8fd4e0bf87e04e2dd1fc1'
$expectedToc = 'c7abce00f8a13f4dd63bad9f9c763cc54424426ecb679c60f0c496d0a95437e8'
$utf8 = New-Object Text.UTF8Encoding($false)

foreach ($required in @($boot,$sourcePack,$sourceToc)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}
if ((Hash $sourcePack) -ne $expectedPack -or (Hash $sourceToc) -ne $expectedToc) {
    throw 'Offline Raven texpack hashes do not match the validated build.'
}

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Raven artwork patch-loading fix is already removed.'
        return
    }
    $m = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath $backupBoot -PathType Leaf)) { throw 'Missing boot backup for patch-loading fix.' }
    $currentBoot = Hash $boot
    if ($currentBoot -ne [string]$m.boot_after -and $currentBoot -ne [string]$m.boot_before) {
        throw 'boot-options.json changed after patch-loading fix. Refusing automatic overwrite.'
    }
    Copy-Item -LiteralPath $backupBoot -Destination $boot -Force
    if ((Hash $boot) -ne [string]$m.boot_before) { throw 'Patch-loading rollback boot hash mismatch.' }

    foreach ($pair in @(@($patchPack,$expectedPack), @($patchToc,$expectedToc))) {
        if (Test-Path -LiteralPath $pair[0] -PathType Leaf) {
            if ((Hash $pair[0]) -ne $pair[1]) { throw "Patch file changed: $($pair[0])" }
            Remove-Item -LiteralPath $pair[0] -Force
        }
    }

    # Restore the underlying artwork layer exactly as it existed before this fix
    # so its own Remove mode remains independently reversible.
    Copy-Item -LiteralPath $sourcePack -Destination $legacyPack -Force
    Copy-Item -LiteralPath $sourceToc -Destination $legacyToc -Force
    if ((Hash $legacyPack) -ne $expectedPack -or (Hash $legacyToc) -ne $expectedToc) {
        throw 'Could not restore legacy artwork-layer texpack files.'
    }

    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Raven artwork patch-loading fix removed.'
    Write-Host 'The previous artwork layer has been restored exactly.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Raven artwork patch-loading fix is already installed.'
}
if (-not (Test-Path -LiteralPath $artManifest -PathType Leaf)) {
    throw 'The Raven artwork layer proof is not active. Install that layer first.'
}
$art = Get-Content -LiteralPath $artManifest -Raw | ConvertFrom-Json
if ($art.texpack_sha256 -ne $expectedPack -or $art.texpack_toc_sha256 -ne $expectedToc) {
    throw 'Active artwork-layer manifest does not match the validated Raven texpack.'
}
foreach ($pair in @(@($legacyPack,$expectedPack), @($legacyToc,$expectedToc))) {
    if (-not (Test-Path -LiteralPath $pair[0] -PathType Leaf)) { throw "Legacy artwork file missing: $($pair[0])" }
    if ((Hash $pair[0]) -ne $pair[1]) { throw "Legacy artwork file hash mismatch: $($pair[0])" }
}
if ((Test-Path -LiteralPath $patchPack) -or (Test-Path -LiteralPath $patchToc)) {
    throw 'Target exec\patch\pc_le Raven texpack already exists outside this fix state.'
}

$bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
$patches = @($bootObj.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
if ($patches -notcontains $legacyEntry) {
    throw "Expected legacy boot entry is missing: $legacyEntry"
}
if ($patches -contains $patchEntry) {
    throw "Correct patch-path entry already exists: $patchEntry"
}

New-Item -ItemType Directory -Force -Path $stateDir,$patchDir | Out-Null
Copy-Item -LiteralPath $boot -Destination $backupBoot -Force
$beforeBoot = Hash $boot

try {
    Copy-Item -LiteralPath $sourcePack -Destination $patchPack -Force
    Copy-Item -LiteralPath $sourceToc -Destination $patchToc -Force
    if ((Hash $patchPack) -ne $expectedPack -or (Hash $patchToc) -ne $expectedToc) {
        throw 'Patch-directory texpack copy hash mismatch.'
    }

    $bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
    $current = @($bootObj.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
    $next = New-Object System.Collections.Generic.List[string]
    foreach ($entry in $current) {
        if ([string]$entry -eq $legacyEntry) {
            if (-not $next.Contains($patchEntry)) { $next.Add($patchEntry) }
        } elseif (-not $next.Contains([string]$entry)) {
            $next.Add([string]$entry)
        }
    }
    $bootObj.'patch-texpacks' = @($next)
    [IO.File]::WriteAllText($boot, ($bootObj | ConvertTo-Json -Depth 30) + [Environment]::NewLine, $utf8)

    $check = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
    $checkEntries = @($check.'patch-texpacks')
    if ($checkEntries -notcontains $patchEntry -or $checkEntries -contains $legacyEntry) {
        throw 'boot-options patch-path migration did not serialize correctly.'
    }

    # Remove the ineffective legacy copies only after the working-path copy and
    # boot entry are fully verified.
    Remove-Item -LiteralPath $legacyPack,$legacyToc -Force

    $afterBoot = Hash $boot
    $manifest = [ordered]@{
        proof = 'v0.10.4 Raven artwork texpack patch-loading path correction'
        cause_under_test = 'bare entry beside exec/wad did not load; use field-proven exec/patch path semantics'
        old_entry = $legacyEntry
        new_entry = $patchEntry
        patch_pack = $patchPack
        patch_toc = $patchToc
        texpack_sha256 = $expectedPack
        texpack_toc_sha256 = $expectedToc
        boot_before = $beforeBoot
        boot_after = $afterBoot
        artwork_layer_remains_active = $true
        game_files_other_than_patch_texpack_and_boot_modified = $false
        save_state_written = $false
        progression_state_written = $false
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 10) + [Environment]::NewLine, $utf8)
}
catch {
    Write-Warning "Patch-loading fix failed; restoring previous artwork-layer state: $($_.Exception.Message)"
    try {
        Copy-Item -LiteralPath $backupBoot -Destination $boot -Force
        Remove-Item -LiteralPath $patchPack,$patchToc -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $legacyPack)) { Copy-Item -LiteralPath $sourcePack -Destination $legacyPack -Force }
        if (-not (Test-Path -LiteralPath $legacyToc)) { Copy-Item -LiteralPath $sourceToc -Destination $legacyToc -Force }
    } catch {
        Write-Warning "Automatic recovery also failed: $($_.Exception.Message)"
    }
    throw
}

Write-Host ''
Write-Host 'Raven artwork patch-loading fix installed.'
Write-Host "- patch files: $patchDir"
Write-Host "- boot entry: $patchEntry"
Write-Host '- underlying dedicated Raven class and prompt fix are unchanged'
Write-Host '- saves/progression are untouched'
Write-Host ''
Write-Host 'Launch God of War and inspect the Raven map marker again.'
