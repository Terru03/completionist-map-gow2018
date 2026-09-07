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
    throw 'Close God of War before scanning the stock DCB set.'
}

$outRel = 'archive/field-logs/completionist-v104-kind35-registration-index.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

python (Join-Path $PSScriptRoot 'inspect-kind35-registration-index.py') `
    --game-root $GameRoot `
    --repo-root $repo `
    --output $out
if ($LASTEXITCODE -ne 0) { throw 'kind-35 registration/index scan failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw 'kind-35 report was not produced.' }

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'kind-35 report unchanged; nothing to commit.'
        return
    }
    git commit -m 'Archive kind-35 compass registration scan' -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    git push $Remote $branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed; commit remains local on $branch." }
    Write-Host "Pushed kind-35 report to $Remote/$branch"
}
finally {
    Pop-Location
}
