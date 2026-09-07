param(
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') {
    throw "Expected feat/v0.10.4-all-ravens, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before inspecting extracted r_ui resources.'
}

$pythonScript = Join-Path $PSScriptRoot 'inspect-map-icon-resource-neighborhood.py'
if (-not (Test-Path -LiteralPath $pythonScript -PathType Leaf)) {
    throw "Missing inspector: $pythonScript"
}
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$extracted = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.4\r_ui-wad-files'
if (-not (Test-Path -LiteralPath $extracted -PathType Container)) {
    throw "Full r_ui extraction not found: $extracted`nRun .\tools\v0.10.4\extract-r-ui-prefab-inventory.ps1 first."
}

$outRel = 'archive/field-logs/completionist-v104-map-icon-resource-neighborhood.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

& $python.Source $pythonScript --extracted $extracted --output $out
if ($LASTEXITCODE -ne 0) {
    throw 'Map-icon resource neighbourhood inspection failed.'
}
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) {
    throw 'Map-icon resource neighbourhood report was not produced.'
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Map-icon resource neighbourhood report unchanged; nothing to commit.'
    }
    else {
        git commit -m 'Archive map icon resource neighbourhood' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) {
            throw "git push failed; the report commit remains local on '$branch'."
        }
        Write-Host "Pushed map-icon resource neighbourhood report to $Remote/$branch"
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Targeted resource-neighbourhood decode complete.'
Write-Host 'No God of War files were modified.'
