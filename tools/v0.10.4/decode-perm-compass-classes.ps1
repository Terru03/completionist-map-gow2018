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
    throw 'Close God of War before running the read-only CompassIconClass decoder.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$archive = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archive | Out-Null
$rel = 'archive/field-logs/completionist-v104-decoded-compass-classes.json'
$out = Join-Path $repo ($rel -replace '/', '\')
$py = Join-Path $PSScriptRoot 'decode-perm-compass-classes.py'

Write-Host 'Decoding permanent CompassIconClass records (read-only)...'
python $py --game-root $GameRoot --output $out
if ($LASTEXITCODE -ne 0) { throw 'CompassIconClass decoder failed.' }

Push-Location $repo
try {
    git add -- $rel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $rel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $rel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Report unchanged; nothing to commit.'
        return
    }
    git commit -m 'Archive decoded CompassIconClass records' -- $rel
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    git push $Remote $branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed; commit remains local on $branch." }
    Write-Host "Pushed decoded CompassIconClass report to $Remote/$branch"
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'No game files were modified.'
