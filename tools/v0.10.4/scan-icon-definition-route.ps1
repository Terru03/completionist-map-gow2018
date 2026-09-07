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
    throw 'Close God of War before running the icon-definition route scan.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$archive = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archive | Out-Null
$rel = 'archive/field-logs/completionist-v104-icon-definition-route.json'
$out = Join-Path $repo ($rel -replace '/', '\')

Write-Host 'Scanning native map/compass icon definition route (read-only)...'
python (Join-Path $PSScriptRoot 'scan-icon-definition-route.py') `
    --game-root $GameRoot `
    --output $out
if ($LASTEXITCODE -ne 0) { throw 'Icon definition route scanner failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf) -or (Get-Item -LiteralPath $out).Length -eq 0) {
    throw 'Icon definition route report is missing or empty.'
}

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

    git commit -m 'Archive v0.10.4 icon definition route scan' -- $rel
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    git push $Remote $branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed; commit remains local on $branch." }
    Write-Host "Pushed icon definition route report to $Remote/$branch"
}
finally {
    Pop-Location
}

Write-Host 'No game files were modified.'
