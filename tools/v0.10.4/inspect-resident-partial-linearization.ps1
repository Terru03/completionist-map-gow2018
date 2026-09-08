param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Expected feat/v0.10.4-all-ravens, got '$branch'." }

$game = [IO.Path]::GetFullPath($GameRoot)
$wad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$rootTexpack = Join-Path $game 'exec\wad\pc_le\root.texpack'
$probe = Join-Path $PSScriptRoot 'inspect-resident-partial-linearization.py'
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
foreach ($p in @($wad,$rootTexpack,$probe)) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Missing required file: $p" }
}

$expectedWad = 'e4a56165e9083eb7d0541699aa404e3e43a0c10aff9f04f1f751b801484e7959'
$currentWad = (Get-FileHash -LiteralPath $wad -Algorithm SHA256).Hash.ToLowerInvariant()
if ($currentWad -ne $expectedWad) {
    throw "r_ui.wad is not the clean registered-Raven base ($currentWad). Remove any active resident-artwork proof first."
}

$outRel = 'archive/field-logs/completionist-v104-resident-partial-linearization.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

& $python.Source -m py_compile $probe
if ($LASTEXITCODE -ne 0) { throw 'Resident partial-linearization probe syntax check failed.' }

& $python.Source $probe --wad $wad --root-texpack $rootTexpack --output $out | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Resident partial-linearization probe failed.' }

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for resident partial-linearization report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive resident partial-linearization proof' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for resident partial-linearization report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for resident partial-linearization report.' }
    } else {
        Write-Host 'Resident partial-linearization report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host 'No God of War files were modified.'
