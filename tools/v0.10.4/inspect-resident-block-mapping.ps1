param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Expected feat/v0.10.4-all-ravens, got '$branch'." }
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before running the read-only resident block mapping probe.' }

$game = [IO.Path]::GetFullPath($GameRoot)
$wad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$rootPack = Join-Path $game 'exec\wad\pc_le\root.texpack'
$probe = Join-Path $PSScriptRoot 'inspect-resident-block-mapping.py'
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
foreach ($required in @($wad,$rootPack,$probe)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}

$outRel = 'archive/field-logs/completionist-v104-resident-block-mapping.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

& $python.Source -m py_compile $probe
if ($LASTEXITCODE -ne 0) { throw 'Resident block mapping probe syntax check failed.' }
& $python.Source $probe --wad $wad --root-texpack $rootPack --output $out | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Resident block mapping probe failed.' }

$report = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ($report.result -ne 'RESIDENT_BLOCK_MAPPING_INSPECTED' -or
    $report.game_files_written -ne $false -or
    $report.save_files_written -ne $false -or
    $report.progression_state_written -ne $false) {
    throw 'Resident block mapping report failed validation.'
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for resident block mapping report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive resident block mapping' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for resident block mapping report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for resident block mapping report.' }
    } else {
        Write-Host 'Resident block mapping report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host 'Read-only resident block mapping complete. No God of War files were modified.'
