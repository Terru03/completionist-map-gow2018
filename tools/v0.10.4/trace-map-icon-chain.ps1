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
    throw 'Close God of War before tracing the map-icon resource chain.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$script = Join-Path $PSScriptRoot 'trace-map-icon-chain.py'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Missing tracer: $script"
}
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$extracted = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.4\r_ui-wad-files'
if (-not (Test-Path -LiteralPath $extracted -PathType Container)) {
    throw "Missing Astra extraction directory: $extracted"
}

$outRel = 'archive/field-logs/completionist-v104-map-icon-chain.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

& $python.Source $script --game-root $GameRoot --extracted $extracted --output $out
if ($LASTEXITCODE -ne 0) {
    throw 'Map-icon chain trace failed.'
}
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) {
    throw 'Map-icon chain report was not produced.'
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Map-icon chain report unchanged; nothing to commit.'
    }
    else {
        git commit -m 'Archive v0.10.4 map icon chain trace' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) {
            throw "git push failed; the report commit remains local on '$branch'."
        }
        Write-Host "Pushed map-icon chain report to $Remote/$branch"
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Read-only trace complete. No God of War files were modified.'
Write-Host 'The report preserves the raw-WAD zero-byte records Astra identified and validates the GOPool append offline only.'
