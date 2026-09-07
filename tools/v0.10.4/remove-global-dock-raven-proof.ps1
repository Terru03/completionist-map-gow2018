param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') {
    throw "Expected feat/v0.10.4-all-ravens, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before removing the old global DockPoint Raven texture proof.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$bootPath = Join-Path $game 'exec\boot-options.json'
if (-not (Test-Path -LiteralPath $bootPath -PathType Leaf)) {
    throw "boot-options.json not found: $bootPath"
}

$stateDir = Join-Path $repo 'build\v0.10.4-remove-global-dock-raven'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$backup = Join-Path $stateDir 'boot-options-before.json'
Copy-Item -LiteralPath $bootPath -Destination $backup -Force

$removeEntries = @(
    '0Completionist_v102_dock_raven',
    'completionist_v102_dock_raven',
    '../../patch/pc_le/completionist_v102_dock_raven'
)

$boot = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
$prop = $boot.PSObject.Properties['patch-texpacks']
$before = @()
if ($null -ne $prop) {
    $before = @($boot.'patch-texpacks' | ForEach-Object { [string]$_ })
    $kept = New-Object 'System.Collections.Generic.List[string]'
    foreach ($entry in $before) {
        if ([string]::IsNullOrWhiteSpace($entry)) { continue }
        if ($removeEntries -contains $entry) { continue }
        if (-not $kept.Contains($entry)) { $kept.Add($entry) }
    }
    $boot.'patch-texpacks' = [string[]]$kept.ToArray()
}

$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($bootPath, (($boot | ConvertTo-Json -Depth 20) + [Environment]::NewLine), $utf8)

$check = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
$after = @($check.'patch-texpacks' | ForEach-Object { [string]$_ })
foreach ($entry in $removeEntries) {
    if ($after -contains $entry) {
        Copy-Item -LiteralPath $backup -Destination $bootPath -Force
        throw "Failed to remove old DockPoint Raven boot entry '$entry'. boot-options.json was restored."
    }
}

$targets = @(
    (Join-Path $game 'exec\wad\pc_le\0Completionist_v102_dock_raven.texpack'),
    (Join-Path $game 'exec\wad\pc_le\0Completionist_v102_dock_raven.texpack.toc'),
    (Join-Path $game 'exec\patch\pc_le\completionist_v102_dock_raven.texpack'),
    (Join-Path $game 'exec\patch\pc_le\completionist_v102_dock_raven.texpack.toc')
)
$removedFiles = @()
foreach ($target in $targets) {
    if (Test-Path -LiteralPath $target -PathType Leaf) {
        Remove-Item -LiteralPath $target -Force
        $removedFiles += $target
    }
}

$manifest = [ordered]@{
    result = 'GLOBAL_DOCKPOINT_RAVEN_PROOF_REMOVED'
    boot_backup = $backup
    removed_boot_entries = @($before | Where-Object { $removeEntries -contains $_ })
    remaining_boot_entries = $after
    removed_files = $removedFiles
    note = 'This intentionally removes only the obsolete global DockPoint Raven texture proof. Real boat docks should return to stock artwork after a full game restart. The Completionist Raven will temporarily lose that global map-art override until the per-Raven visual route is implemented.'
}
[IO.File]::WriteAllText((Join-Path $stateDir 'result.json'), ($manifest | ConvertTo-Json -Depth 6), $utf8)

Write-Host 'Removed the obsolete global DockPoint Raven texture proof.'
Write-Host "Removed boot entries: $((@($manifest.removed_boot_entries) -join ', '))"
Write-Host "Removed proof files: $($removedFiles.Count)"
Write-Host 'Real boat docks should use stock artwork again after a full God of War restart.'
Write-Host 'The Completionist Raven may also show stock DockPoint art temporarily; that is expected until per-Raven art is isolated.'
Write-Host "Boot backup: $backup"
