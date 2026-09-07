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
    throw 'God of War is running. Close the game before repairing patch-texpack loading.'
}

$mapBase = '0Completionist_v102_dock_raven'
$hudBase = '0Completionist_v102_hud_r3l3_raven'
$wadDir = Join-Path $GameRoot 'exec\wad\pc_le'
$mapPack = Join-Path $wadDir ($mapBase + '.texpack')
$mapToc = Join-Path $wadDir ($mapBase + '.texpack.toc')
$hudPack = Join-Path $wadDir ($hudBase + '.texpack')
$hudToc = Join-Path $wadDir ($hudBase + '.texpack.toc')

foreach ($required in @($mapPack, $mapToc, $hudPack, $hudToc)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required proof file is missing: $required"
    }
}

$bootPath = Join-Path $GameRoot 'exec\boot-options.json'
if (-not (Test-Path -LiteralPath $bootPath)) { throw "boot-options.json not found: $bootPath" }
$backup = "$bootPath.completionist-v102-before-hud-boot-repair.bak"
if (-not (Test-Path -LiteralPath $backup)) {
    Copy-Item -LiteralPath $bootPath -Destination $backup
}

$boot = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
$rawEntries = @()
$prop = $boot.PSObject.Properties['patch-texpacks']
if ($null -ne $prop) {
    $rawEntries = @($boot.'patch-texpacks')
}

$malformedForward = $mapBase + $hudBase
$malformedReverse = $hudBase + $mapBase
$normalized = New-Object 'System.Collections.Generic.List[string]'
$repairedMalformed = $false

foreach ($entryObj in $rawEntries) {
    if ($null -eq $entryObj) { continue }
    $entry = [string]$entryObj
    if ([string]::IsNullOrWhiteSpace($entry)) { continue }

    if ($entry -eq $malformedForward -or $entry -eq $malformedReverse) {
        $repairedMalformed = $true
        continue
    }

    if (-not $normalized.Contains($entry)) {
        $normalized.Add($entry)
    }
}

if (-not $normalized.Contains($mapBase)) { $normalized.Add($mapBase) }
if (-not $normalized.Contains($hudBase)) { $normalized.Add($hudBase) }

$newEntries = [string[]]$normalized.ToArray()
if ($null -eq $prop) {
    $boot | Add-Member -NotePropertyName 'patch-texpacks' -NotePropertyValue $newEntries
}
else {
    $boot.'patch-texpacks' = $newEntries
}

$json = $boot | ConvertTo-Json -Depth 20
$utf8NoBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($bootPath, $json + [Environment]::NewLine, $utf8NoBom)

$check = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
$checkEntries = @($check.'patch-texpacks')
if ($checkEntries -notcontains $mapBase) {
    throw "Map Raven proof entry is missing after repair: $mapBase"
}
if ($checkEntries -notcontains $hudBase) {
    throw "HUD Raven proof entry is missing after repair: $hudBase"
}
if ($checkEntries -contains $malformedForward -or $checkEntries -contains $malformedReverse) {
    throw 'Malformed concatenated Completionist proof entry remains after repair.'
}

# Persist the PowerShell 5.1 scalar/array fix into the proof installer itself.
$installerRelative = 'tools/v0.10.2/build-install-hud-r3l3-raven-proof.ps1'
$installerPath = Join-Path $repo ($installerRelative -replace '/', '\')
if (-not (Test-Path -LiteralPath $installerPath)) {
    throw "HUD proof installer not found: $installerPath"
}

$installerText = [IO.File]::ReadAllText($installerPath)
$oldBlock = @'
    $current = @($boot.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
    if ($current -notcontains $packBase) {
        $boot.'patch-texpacks' = @($current + $packBase)
    }
'@
$newBlock = @'
    $current = @(
        @($boot.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
    )
    if ($current -notcontains $packBase) {
        $nextEntries = @($current)
        $nextEntries += [string]$packBase
        $boot.'patch-texpacks' = [string[]]$nextEntries
    }
'@

$installerPatched = $false
if ($installerText.Contains($oldBlock)) {
    $installerText = $installerText.Replace($oldBlock, $newBlock)
    [IO.File]::WriteAllText($installerPath, $installerText, $utf8NoBom)
    $installerPatched = $true
}
elseif (-not $installerText.Contains('$nextEntries += [string]$packBase')) {
    throw 'Could not recognise the HUD proof installer boot-entry block. Refusing to patch it.'
}

$reportDir = Join-Path $repo 'archive\field-logs'
$report = Join-Path $reportDir 'completionist-v102-hud-r3l3-boot-repair.txt'
New-Item -ItemType Directory -Force $reportDir | Out-Null

$lines = @(
    '=== Completionist Map v0.10.2 HUD R3_L3 boot-entry repair ==='
    "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    "Branch: $branch"
    "GameRoot: $GameRoot"
    ''
    '=== reason ==='
    'Windows PowerShell 5.1 collapsed a one-item pipeline result to a scalar string.'
    'The original HUD proof installer then used string + string instead of array + element,'
    'creating one concatenated patch-texpacks entry.'
    ''
    '=== repair ==='
    "Malformed concatenation detected: $repairedMalformed"
    "Map proof entry: $mapBase"
    "HUD proof entry: $hudBase"
    "Final patch-texpacks count: $($checkEntries.Count)"
    "Final entries: $($checkEntries -join ', ')"
    "Backup: $backup"
    "Installer source patched: $installerPatched"
    ''
    '=== installed proof packs ==='
    "Map texpack: $mapPack"
    "HUD texpack: $hudPack"
    ''
    'Both proof packs are now referenced as separate boot entries.'
    'The proof installer now forces array semantics before appending future entries.'
    'No Kratos/Omega texture hashes are involved in this repair.'
)
$lines | Set-Content -LiteralPath $report -Encoding UTF8

Write-Host ''
Write-Host 'Repaired v0.10.2 patch-texpacks entries.'
Write-Host "Malformed concatenation detected: $repairedMalformed"
Write-Host "Final entries: $($checkEntries -join ', ')"
Write-Host "Installer source patched: $installerPatched"
Write-Host "Saved report: $report"
Write-Host 'Fully restart God of War before testing.'

$relativeReport = 'archive/field-logs/completionist-v102-hud-r3l3-boot-repair.txt'
& git add -- $relativeReport $installerRelative
if ($LASTEXITCODE -ne 0) { throw 'git add failed for the HUD boot repair changes.' }
& git diff --cached --quiet -- $relativeReport $installerRelative
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Repair state is unchanged. Nothing to commit.'
    exit 0
}
& git commit -m 'Fix v0.10.2 HUD proof boot entry handling' -- $relativeReport $installerRelative
if ($LASTEXITCODE -ne 0) { throw 'git commit failed for the HUD boot repair changes.' }
& git push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw "git push failed. The repair commit exists locally on '$branch'." }
Write-Host "Pushed HUD boot repair and installer fix to $Remote/$branch"
