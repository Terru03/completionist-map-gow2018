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
    throw 'Close God of War before running the permanent compass layout scan.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$rel = 'archive/field-logs/completionist-v104-wad-r-perm-compass-layout.json'
$out = Join-Path $repo ($rel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

Write-Host 'Inspecting wad_r_perm.dcb compass-class layout (read-only)...'
python (Join-Path $PSScriptRoot 'inspect-perm-compass-layout.py') `
    --game-root $GameRoot `
    --output $out
if ($LASTEXITCODE -ne 0) { throw 'Permanent compass layout inspector failed.' }

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

    git commit -m 'Archive v0.10.4 permanent compass layout scan' -- $rel
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }

    git push $Remote $branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed; commit remains local on '$branch'." }

    Write-Host "Pushed permanent compass layout report to $Remote/$branch"
}
finally {
    Pop-Location
}

Write-Host 'No game files were modified.'
