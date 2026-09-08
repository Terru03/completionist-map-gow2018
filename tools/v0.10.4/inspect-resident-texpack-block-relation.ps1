param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Expected feat/v0.10.4-all-ravens, got '$branch'." }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$game = [IO.Path]::GetFullPath($GameRoot)
$wad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$rootPack = Join-Path $game 'exec\wad\pc_le\root.texpack'
$probe = Join-Path $PSScriptRoot 'inspect-resident-texpack-block-relation.py'
$outRel = 'archive/field-logs/completionist-v104-resident-texpack-block-relation.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

foreach ($required in @($wad,$rootPack,$probe)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}

& $python.Source -m py_compile $probe
if ($LASTEXITCODE -ne 0) { throw 'Resident/texpack relation probe syntax check failed.' }

New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null
& $python.Source $probe `
    --wad $wad `
    --root-texpack $rootPack `
    --output $out | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Resident/texpack relation probe failed.' }

$r = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ($r.result -ne 'RESIDENT_TEXPACK_BLOCK_RELATION_INSPECTED' -or
    $r.game_files_written -ne $false -or
    $r.save_files_written -ne $false -or
    $r.progression_state_written -ne $false) {
    throw 'Resident/texpack relation report failed validation.'
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for resident/texpack relation report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive resident texpack block relation' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for resident/texpack relation report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for resident/texpack relation report.' }
    } else {
        Write-Host 'Resident/texpack relation report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Resident/texpack block relation probe complete.'
Write-Host '- read-only against r_ui.wad and root.texpack'
Write-Host '- no saves, boot options, progression or marker state modified'
Write-Host "- report: $outRel"
