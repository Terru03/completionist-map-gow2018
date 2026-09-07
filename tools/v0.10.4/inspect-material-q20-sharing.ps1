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
    throw 'Close God of War before running the material q20 sharing inspector.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$script = Join-Path $PSScriptRoot 'inspect-material-q20-sharing.py'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Missing inspector: $script"
}
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$outRel = 'archive/field-logs/completionist-v104-material-q20-sharing.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

& $python.Source -m py_compile $script
if ($LASTEXITCODE -ne 0) {
    throw 'Python syntax check failed for material q20 sharing inspector.'
}

& $python.Source $script --game-root $GameRoot --output $out
if ($LASTEXITCODE -ne 0) {
    throw 'Material q20 sharing inspection failed.'
}
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) {
    throw 'Material q20 sharing report was not produced.'
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Material q20 sharing report unchanged; nothing to commit.'
    }
    else {
        git commit -m 'Archive material q20 sharing evidence' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) {
            throw "git push failed; the evidence commit remains local on '$branch'."
        }
        Write-Host "Pushed material q20 sharing evidence to $Remote/$branch"
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Material q20 sharing inspection complete.'
Write-Host 'No God of War files were modified.'
