param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'

$repo = (& git rev-parse --show-toplevel).Trim()
if (-not $repo) {
    throw 'Run this script from inside the Completionist Map Git repository.'
}

$branch = (& git branch --show-current).Trim()
if (-not $branch) {
    throw 'Detached HEAD is not supported.'
}

if (-not (Test-Path $GameRoot)) {
    throw "God of War root not found: $GameRoot"
}

$outDir = Join-Path $repo 'archive\field-logs'
$out = Join-Path $outDir 'completionist-v102-container-inventory.txt'
New-Item -ItemType Directory -Force $outDir | Out-Null

$containerRoots = @(
    (Join-Path $GameRoot 'exec\wad\pc_le'),
    (Join-Path $GameRoot 'exec\wad'),
    (Join-Path $GameRoot 'exec\patch\pc_le'),
    (Join-Path $GameRoot 'exec\patch')
) | Where-Object { Test-Path $_ } | Select-Object -Unique

$interestingRegex = '(?i)(ui|hud|map|menu|shell|pause|icon|marker|compass|frontend|interface)'
$containerRegex = '(?i)\.(texpack|texpack\.toc|wad|wad\.toc|lodpack|lodpack\.toc)$'

$containers = @()
foreach ($root in $containerRoots) {
    Write-Host "Scanning container names under: $root"
    $containers += Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match $containerRegex }
}

$containers = @($containers | Sort-Object FullName -Unique)

$topExec = @()
$execRoot = Join-Path $GameRoot 'exec'
if (Test-Path $execRoot) {
    $topExec = @(Get-ChildItem -LiteralPath $execRoot -Force -ErrorAction SilentlyContinue |
        Sort-Object @{ Expression = { $_.PSIsContainer }; Descending = $true },
                    @{ Expression = { $_.Name }; Descending = $false })
}

$bootOptionsPath = Join-Path $GameRoot 'exec\boot-options.json'
$patchTexpacks = @()
$bootParseError = $null
if (Test-Path $bootOptionsPath) {
    try {
        $boot = Get-Content -LiteralPath $bootOptionsPath -Raw | ConvertFrom-Json
        $patchTexpacks = @($boot.'patch-texpacks')
    }
    catch {
        $bootParseError = $_.Exception.Message
    }
}

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('=== Completionist Map v0.10.2 container inventory ===')
$lines.Add("Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')")
$lines.Add("GameRoot: $GameRoot")
$lines.Add("Branch: $branch")
$lines.Add('')

$lines.Add('=== exec top-level ===')
foreach ($item in $topExec) {
    $kind = if ($item.PSIsContainer) { 'DIR ' } else { 'FILE' }
    $size = if ($item.PSIsContainer) { '' } else { ('{0:N2} MiB' -f ($item.Length / 1MB)) }
    $lines.Add(('{0}  {1,-12}  {2}' -f $kind, $size, $item.Name))
}
$lines.Add('')

$lines.Add('=== boot-options patch-texpacks ===')
if (-not (Test-Path $bootOptionsPath)) {
    $lines.Add('boot-options.json not found')
}
elseif ($bootParseError) {
    $lines.Add("Could not parse boot-options.json: $bootParseError")
}
elseif ($patchTexpacks.Count -eq 0) {
    $lines.Add('<empty>')
}
else {
    foreach ($entry in $patchTexpacks) {
        $lines.Add([string]$entry)
    }
}
$lines.Add('')

$lines.Add('=== container counts ===')
$groups = @($containers | Group-Object {
    $n = $_.Name.ToLowerInvariant()
    if ($n.EndsWith('.texpack.toc')) { '.texpack.toc' }
    elseif ($n.EndsWith('.texpack')) { '.texpack' }
    elseif ($n.EndsWith('.wad.toc')) { '.wad.toc' }
    elseif ($n.EndsWith('.wad')) { '.wad' }
    elseif ($n.EndsWith('.lodpack.toc')) { '.lodpack.toc' }
    elseif ($n.EndsWith('.lodpack')) { '.lodpack' }
    else { '<other>' }
} | Sort-Object Name)
foreach ($g in $groups) {
    $lines.Add(('{0,-14} {1,6}' -f $g.Name, $g.Count))
}
$lines.Add("TOTAL          $($containers.Count)")
$lines.Add('')

$lines.Add('=== likely UI / map containers ===')
$likely = @($containers | Where-Object { $_.FullName -match $interestingRegex })
if ($likely.Count -eq 0) {
    $lines.Add('<none matched by filename>')
}
else {
    foreach ($file in $likely) {
        $relative = $file.FullName.Substring($GameRoot.Length).TrimStart('\')
        $lines.Add(('{0,10:N2} MiB  {1}' -f ($file.Length / 1MB), $relative))
    }
}
$lines.Add('')

$lines.Add('=== all texpack files ===')
$texpacks = @($containers | Where-Object { $_.Name -match '(?i)\.texpack$' })
foreach ($file in $texpacks) {
    $relative = $file.FullName.Substring($GameRoot.Length).TrimStart('\')
    $lines.Add(('{0,10:N2} MiB  {1}' -f ($file.Length / 1MB), $relative))
}
$lines.Add('')

$lines.Add('=== likely UI / map WAD files ===')
$likelyWads = @($containers | Where-Object {
    $_.Name -match '(?i)\.wad$' -and $_.FullName -match $interestingRegex
})
if ($likelyWads.Count -eq 0) {
    $lines.Add('<none matched by filename>')
}
else {
    foreach ($file in $likelyWads) {
        $relative = $file.FullName.Substring($GameRoot.Length).TrimStart('\')
        $lines.Add(('{0,10:N2} MiB  {1}' -f ($file.Length / 1MB), $relative))
    }
}
$lines.Add('')

$lines.Add('=== notes ===')
$lines.Add('This report records filenames and sizes only. It does not modify game files.')
$lines.Add('The next step is to select likely map/UI texpacks for GOWTool extraction.')

$lines | Set-Content -LiteralPath $out -Encoding UTF8
Write-Host "Saved inventory: $out"
Write-Host "Containers found: $($containers.Count)"
Write-Host "Likely UI/map containers: $($likely.Count)"
Write-Host "Texpacks: $($texpacks.Count)"

$relativeOut = 'archive/field-logs/completionist-v102-container-inventory.txt'
& git add -- $relativeOut
if ($LASTEXITCODE -ne 0) {
    throw 'git add failed for the v0.10.2 inventory.'
}

& git diff --cached --quiet -- $relativeOut
$hasChanges = $LASTEXITCODE -ne 0
if (-not $hasChanges) {
    Write-Host 'Inventory is unchanged. Nothing to commit.'
    exit 0
}

& git commit -m 'Archive v0.10.2 UI container inventory' -- $relativeOut
if ($LASTEXITCODE -ne 0) {
    throw 'git commit failed for the v0.10.2 inventory.'
}

& git push $Remote $branch
if ($LASTEXITCODE -ne 0) {
    throw "git push failed. The inventory commit exists locally on '$branch'."
}

Write-Host "Pushed inventory to $Remote/$branch"
