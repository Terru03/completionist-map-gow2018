param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$ToolPath = "$env:LOCALAPPDATA\CompletionistMap\tools\GOWTool-v0.1.3-alpha\GOWTool.exe",
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') {
    throw "Expected feat/v0.10.4-all-ravens, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before extracting r_ui.wad for the prefab inventory.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}
if (-not (Test-Path -LiteralPath $ToolPath -PathType Leaf)) {
    throw "GOWTool not found: $ToolPath"
}

$wad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
if (-not (Test-Path -LiteralPath $wad -PathType Leaf)) {
    throw "r_ui.wad not found: $wad"
}

$pythonScript = Join-Path $PSScriptRoot 'inspect-r-ui-prefab-extract.py'
if (-not (Test-Path -LiteralPath $pythonScript -PathType Leaf)) {
    throw "Missing inspector: $pythonScript"
}
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$workRoot = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.4'
$outDir = Join-Path $workRoot 'r_ui-wad-files'
Remove-Item -LiteralPath $outDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

Write-Host 'Extracting all r_ui.wad buffers to LocalAppData for read-only inspection...'
Write-Host "WAD: $wad"
Write-Host "Output: $outDir"

# GOWTool writes its config beside the executable. Run from that directory.
$toolDir = Split-Path -Parent $ToolPath
Push-Location $toolDir
try {
    $toolOutput = @(& $ToolPath wad -p $wad -o $outDir -e 2>&1)
    $toolExit = $LASTEXITCODE
}
finally {
    Pop-Location
}
if ($toolExit -ne 0) {
    $toolOutput | ForEach-Object { Write-Host $_ }
    throw "GOWTool r_ui.wad extraction failed with exit code $toolExit."
}

$extracted = @(Get-ChildItem -LiteralPath $outDir -File -Recurse -ErrorAction SilentlyContinue)
if ($extracted.Count -eq 0) {
    throw 'GOWTool completed but extracted no files.'
}

$outRel = 'archive/field-logs/completionist-v104-r-ui-prefab-inventory.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

& $python.Source $pythonScript --extracted $outDir --wad $wad --output $out
if ($LASTEXITCODE -ne 0) {
    throw 'r_ui prefab extraction inspection failed.'
}
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) {
    throw 'r_ui prefab inventory report was not produced.'
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'r_ui prefab inventory unchanged; nothing to commit.'
    }
    else {
        git commit -m 'Archive r_ui prefab extraction inventory' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) {
            throw "git push failed; the report commit remains local on '$branch'."
        }
        Write-Host "Pushed r_ui prefab inventory to $Remote/$branch"
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host "Extracted buffers: $($extracted.Count)"
Write-Host 'Extraction lives only under LocalAppData and is not committed.'
Write-Host 'No God of War files were modified.'
