param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'

$repo = (& git rev-parse --show-toplevel).Trim()
if (-not $repo) { throw 'Run this script from inside the Completionist Map Git repository.' }
$branch = (& git branch --show-current).Trim()
if (-not $branch) { throw 'Detached HEAD is not supported.' }
if (-not (Test-Path -LiteralPath $GameRoot)) { throw "God of War root not found: $GameRoot" }
if (Get-Process -Name 'GoW' -ErrorAction SilentlyContinue) {
    throw 'God of War is running. Close the game before changing texpack loading.'
}

$sourceDir = Join-Path $GameRoot 'exec\patch\pc_le'
$sourceBase = 'completionist_v102_dock_raven'
$sourcePack = Join-Path $sourceDir ($sourceBase + '.texpack')
$sourceToc = Join-Path $sourceDir ($sourceBase + '.texpack.toc')
foreach ($required in @($sourcePack, $sourceToc)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Verified source pack is missing: $required" }
}

# Use the alternate layout used by many working PC texture mods:
# exec\wad\pc_le\<pack>.texpack with a bare pack name in patch-texpacks.
$wadDir = Join-Path $GameRoot 'exec\wad\pc_le'
$targetBase = '0Completionist_v102_dock_raven'
$targetPack = Join-Path $wadDir ($targetBase + '.texpack')
$targetToc = Join-Path $wadDir ($targetBase + '.texpack.toc')

Copy-Item -LiteralPath $sourcePack -Destination $targetPack -Force
Copy-Item -LiteralPath $sourceToc -Destination $targetToc -Force

$sourceHash = (Get-FileHash -LiteralPath $sourcePack -Algorithm SHA256).Hash
$targetHash = (Get-FileHash -LiteralPath $targetPack -Algorithm SHA256).Hash
if ($sourceHash -ne $targetHash) { throw 'Copied WAD texpack does not match the verified source texpack.' }

$bootPath = Join-Path $GameRoot 'exec\boot-options.json'
if (-not (Test-Path -LiteralPath $bootPath)) { throw "boot-options.json not found: $bootPath" }
$backup = "$bootPath.completionist-v102-before-wad-loader-proof.bak"
if (-not (Test-Path -LiteralPath $backup)) {
    Copy-Item -LiteralPath $bootPath -Destination $backup
}

$boot = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
$prop = $boot.PSObject.Properties['patch-texpacks']
if ($null -eq $prop) {
    $boot | Add-Member -NotePropertyName 'patch-texpacks' -NotePropertyValue @($targetBase)
}
else {
    # Deliberately use only the alternate proof pack for this isolated loader test.
    $boot.'patch-texpacks' = @($targetBase)
}

$json = $boot | ConvertTo-Json -Depth 20
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($bootPath, $json + [Environment]::NewLine, $utf8NoBom)

$check = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
$entries = @($check.'patch-texpacks')
if ($entries.Count -ne 1 -or $entries[0] -ne $targetBase) {
    throw 'boot-options.json did not retain the expected WAD-loader proof entry.'
}

$reportDir = Join-Path $repo 'archive\field-logs'
$report = Join-Path $reportDir 'completionist-v102-dock-raven-wad-loader-proof.txt'
New-Item -ItemType Directory -Force $reportDir | Out-Null

$lines = @(
    '=== Completionist Map v0.10.2 DockPoint Raven WAD-loader proof ==='
    "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    "Branch: $branch"
    "GameRoot: $GameRoot"
    ''
    '=== verified source pack ==='
    "Source: $sourcePack"
    "SHA256: $sourceHash"
    ''
    '=== alternate installed location ==='
    "Texpack: $targetPack"
    "TOC: $targetToc"
    "SHA256: $targetHash"
    "boot-options entry: $targetBase"
    "boot-options backup: $backup"
    ''
    '=== purpose ==='
    'This is the same already-verified two-texture DockPoint Raven pack, copied to exec\\wad\\pc_le.'
    'patch-texpacks now references the bare pack name to test alternate loader resolution/precedence.'
    'No Kratos/Omega texture hashes are contained in this pack.'
    ''
    '=== expected runtime result ==='
    'If this loader form is honoured, stock DockPoint map icons and Completionist DockPoint proxies will show Raven artwork.'
    'If boats remain unchanged, the remaining suspect is runtime texture override semantics rather than pack path or hash construction.'
)
$lines | Set-Content -LiteralPath $report -Encoding UTF8

Write-Host ''
Write-Host 'Installed alternate WAD-loader DockPoint Raven proof.'
Write-Host "Texpack: $targetPack"
Write-Host "boot-options patch-texpacks: [$targetBase]"
Write-Host "Saved report: $report"
Write-Host 'Fully restart God of War before testing.'

$relativeReport = 'archive/field-logs/completionist-v102-dock-raven-wad-loader-proof.txt'
& git add -- $relativeReport
if ($LASTEXITCODE -ne 0) { throw 'git add failed for the WAD-loader proof report.' }
& git diff --cached --quiet -- $relativeReport
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Report is unchanged. Nothing to commit.'
    exit 0
}
& git commit -m 'Archive v0.10.2 WAD-loader texture proof' -- $relativeReport
if ($LASTEXITCODE -ne 0) { throw 'git commit failed for the WAD-loader proof report.' }
& git push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw "git push failed. The report commit exists locally on '$branch'." }
Write-Host "Pushed WAD-loader proof report to $Remote/$branch"
