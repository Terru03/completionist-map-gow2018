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
    throw 'Close God of War before running the Raven material/texture isolation inspection.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
$script = Join-Path $PSScriptRoot 'inspect-raven-material-texture-isolation.py'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Missing inspector: $script" }

$ddsDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.2\r_ui-dds'
$ddsCount = 0
if (Test-Path -LiteralPath $ddsDir -PathType Container) {
    $ddsCount = @(Get-ChildItem -LiteralPath $ddsDir -Filter '*.dds' -File -ErrorAction SilentlyContinue).Count
}
if ($ddsCount -lt 1000) {
    $gowTool = Join-Path $env:LOCALAPPDATA 'CompletionistMap\tools\GOWTool-v0.1.3-alpha\GOWTool.exe'
    if (-not (Test-Path -LiteralPath $gowTool -PathType Leaf)) {
        throw "GOWTool missing: $gowTool"
    }
    $wad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
    Remove-Item -LiteralPath $ddsDir -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $ddsDir | Out-Null
    Write-Host 'Rebuilding local r_ui DDS inventory because a complete prior extraction was not found...'
    Push-Location (Split-Path -Parent $gowTool)
    try {
        & $gowTool wad -p $wad -o $ddsDir -t -d
        if ($LASTEXITCODE -ne 0) { throw "GOWTool texture extraction failed with exit code $LASTEXITCODE" }
    }
    finally {
        Pop-Location
    }
    $ddsCount = @(Get-ChildItem -LiteralPath $ddsDir -Filter '*.dds' -File -ErrorAction SilentlyContinue).Count
    if ($ddsCount -lt 1000) { throw "Expected a full r_ui DDS extraction; found only $ddsCount files." }
}
Write-Host "Using local DDS inventory: $ddsDir ($ddsCount files)"

$outRel = 'archive/field-logs/completionist-v104-raven-material-texture-isolation.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

& $python.Source $script --game-root $GameRoot --dds-dir $ddsDir --output $out
if ($LASTEXITCODE -ne 0) { throw 'Raven material/texture isolation inspection failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw 'Isolation report was not produced.' }

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Isolation report unchanged; nothing to commit.'
    }
    else {
        git commit -m 'Archive Raven material texture isolation scan' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw "git push failed; report commit remains local on '$branch'." }
        Write-Host "Pushed Raven material/texture isolation report to $Remote/$branch"
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Raven material/texture isolation inspection complete.'
Write-Host 'No God of War files were modified.'
