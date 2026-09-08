param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Expected feat/v0.10.4-all-ravens, got '$branch'." }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

$wad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$rootPack = Join-Path $GameRoot 'exec\wad\pc_le\root.texpack'
$probe = Join-Path $PSScriptRoot 'inspect-resident-composite-permutation.py'
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
foreach ($required in @($wad,$rootPack,$probe)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}

$outRel = 'archive/field-logs/completionist-v104-resident-composite-permutation.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

& $python.Source -m py_compile $probe
if ($LASTEXITCODE -ne 0) { throw 'Resident composite permutation probe syntax check failed.' }

& $python.Source $probe `
    --wad $wad `
    --root-texpack $rootPack `
    --output $out | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Resident composite permutation probe failed.' }

$r = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ($r.result -ne 'RESIDENT_COMPOSITE_PERMUTATION_INSPECTED' -or
    $r.game_files_written -ne $false -or
    $r.save_files_written -ne $false -or
    $r.progression_state_written -ne $false) {
    throw 'Resident composite permutation report failed validation.'
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for resident composite permutation report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive resident composite permutation' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for resident composite permutation report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for resident composite permutation report.' }
    } else {
        Write-Host 'Resident composite permutation report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host ('runtime_patch_gate: ' + [string]$r.runtime_patch_gate)
Write-Host ('unique resident/source keys: {0}/{1}' -f $r.composite.resident_unique_keys, $r.composite.source_unique_keys)
Write-Host ('ambiguous key groups: ' + [string]$r.composite.ambiguous_key_groups)
Write-Host ('reconstructs all four stock residents: ' + [string]$r.permutation.reconstructs_all_four_stock_residents)
Write-Host 'No God of War files were modified.'
