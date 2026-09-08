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
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before running the registered map-class inventory.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$wad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$dcb = Join-Path $game 'exec\dc\pc_le\wad_r_ui.dcb'
$mapmaster = Join-Path $game 'exec\dc\pc_le\mapmaster.dcb'
$py = Join-Path $PSScriptRoot 'inspect-r-ui-registered-map-classes.py'
$outRel = 'archive/field-logs/completionist-v104-registered-r-ui-map-classes.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

foreach ($required in @($wad,$dcb,$mapmaster,$py)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing required file: $required"
    }
}
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

& $python.Source -m py_compile $py
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed.' }

& $python.Source $py `
    --r-ui-wad $wad `
    --wad-r-ui-dcb $dcb `
    --mapmaster $mapmaster `
    --output $out
if ($LASTEXITCODE -ne 0) { throw 'Registered map-class inventory failed.' }

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for map-class inventory report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive registered r_ui map class inventory' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for map-class inventory report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for map-class inventory report.' }
    } else {
        Write-Host 'Registered map-class inventory unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Registered r_ui map-class inventory complete.'
Write-Host 'No God of War files were modified.'
