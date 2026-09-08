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

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$wad = Join-Path ([IO.Path]::GetFullPath($GameRoot)) 'exec\wad\pc_le\r_ui.wad'
$probe = Join-Path $PSScriptRoot 'inspect-map-icon-resident-textures.py'
$outRel = 'archive/field-logs/completionist-v104-map-icon-resident-textures.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

foreach ($required in @($wad,$probe)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}

& $python.Source -m py_compile $probe
if ($LASTEXITCODE -ne 0) { throw 'Resident texture inventory syntax check failed.' }

& $python.Source $probe --wad $wad --output $out | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Resident texture inventory failed.' }

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for resident texture inventory.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive resident map icon texture inventory' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for resident texture inventory.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for resident texture inventory.' }
    } else {
        Write-Host 'Resident texture inventory unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host "Saved: $out"
Write-Host 'Read-only probe complete. No God of War files, saves, boot options or progression state were modified.'
