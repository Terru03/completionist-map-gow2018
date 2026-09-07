param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') {
    throw "Expected feat/v0.10.4-all-ravens, got '$branch'."
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$archive = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archive | Out-Null

$mapRel = 'archive/field-logs/completionist-v104-map-icon-usage.json'
$classRel = 'archive/field-logs/completionist-v104-compass-icon-classes.json'
$mapOut = Join-Path $repo ($mapRel -replace '/', '\')
$classOut = Join-Path $repo ($classRel -replace '/', '\')

Write-Host 'Scanning stock map icon usage (read-only)...'
python (Join-Path $PSScriptRoot 'scan-map-icon-instances.py') `
    --game-root $GameRoot `
    --output $mapOut
if ($LASTEXITCODE -ne 0) { throw 'Map icon usage scanner failed.' }

Write-Host ''
Write-Host 'Scanning DCBs for CompassIconClass evidence (read-only)...'
python (Join-Path $PSScriptRoot 'scan-compass-icon-classes.py') `
    --game-root $GameRoot `
    --output $classOut
if ($LASTEXITCODE -ne 0) { throw 'Compass icon class scanner failed.' }

Push-Location $repo
try {
    git add -- $mapRel $classRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }

    git diff --cached --check -- $mapRel $classRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $mapRel $classRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Reports unchanged; nothing to commit.'
        return
    }

    git commit -m 'Archive v0.10.4 Raven icon separation scan' -- $mapRel $classRel
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }

    git push $Remote $branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed; commit remains local on $branch." }

    Write-Host "Pushed icon separation reports to $Remote/$branch"
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'No game files were modified.'
