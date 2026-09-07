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

$buildRoot = Join-Path $repo 'build\v0.10.4-dedicated-raven-class'
$output = Join-Path $buildRoot 'game-root\exec\dc\pc_le\wad_r_perm.dcb'
$reportRel = 'archive/field-logs/completionist-v104-offline-raven-compass-class.json'
$report = Join-Path $repo ($reportRel -replace '/', '\')

Remove-Item -LiteralPath $buildRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Split-Path $output -Parent) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $report -Parent) | Out-Null

python (Join-Path $PSScriptRoot 'build-dedicated-raven-compass-class.py') `
    --game-root $GameRoot `
    --output $output `
    --report $report
if ($LASTEXITCODE -ne 0) {
    throw 'Offline dedicated Raven CompassIconClass build failed.'
}
if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
    throw 'Offline patched wad_r_perm.dcb was not produced.'
}
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw 'Offline build report was not produced.'
}

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }

    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Offline report unchanged; nothing to commit.'
        return
    }

    git commit -m 'Archive offline dedicated Raven compass class proof' -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }

    git push $Remote $branch
    if ($LASTEXITCODE -ne 0) {
        throw "git push failed; commit remains local on $branch."
    }
    Write-Host "Pushed offline class report to $Remote/$branch"
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Offline only. No God of War files were modified.'
Write-Host "Patched proof copy: $output"
