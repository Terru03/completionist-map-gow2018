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
    throw 'Close God of War before decoding the stock r_ui map-icon layout.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$script = Join-Path $PSScriptRoot 'decode-r-ui-map-icon-layout.py'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Missing decoder: $script"
}
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$outRel = 'archive/field-logs/completionist-v104-r-ui-map-icon-layout.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

& $python.Source $script --game-root $GameRoot --output $out
if ($LASTEXITCODE -ne 0) {
    throw 'r_ui map-icon layout decode failed.'
}
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) {
    throw 'r_ui map-icon layout report was not produced.'
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'r_ui map-icon layout report unchanged; nothing to commit.'
    }
    else {
        git commit -m 'Archive r_ui map icon layout decode' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) {
            throw "git push failed; the report commit remains local on '$branch'."
        }
        Write-Host "Pushed r_ui map-icon layout report to $Remote/$branch"
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Targeted read-only decode complete. No God of War files were modified.'
Write-Host 'This does not install or test a custom CompassIconClass.'
