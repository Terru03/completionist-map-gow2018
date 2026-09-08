param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin',
    [switch]$NoPublish
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}

$python = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $python) { throw 'Python 3.9+ required.' }

$tool = Join-Path $PSScriptRoot 'inspect-dockpoint-hud-resource-chain.py'
if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) { throw "Missing tool: $tool" }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

$outRel = 'archive/field-logs/completionist-v104-dockpoint-hud-resource-chain.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

$wad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$perm = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_perm.dcb'
$wadBefore = (Get-FileHash -LiteralPath $wad -Algorithm SHA256).Hash.ToLowerInvariant()
$permBefore = (Get-FileHash -LiteralPath $perm -Algorithm SHA256).Hash.ToLowerInvariant()

& $python.Source -m py_compile $tool
if ($LASTEXITCODE -ne 0) { throw 'HUD resource-chain resolver syntax check failed.' }

& $python.Source $tool --game-root $GameRoot --output $out | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'HUD resource-chain resolver failed.' }

$wadAfter = (Get-FileHash -LiteralPath $wad -Algorithm SHA256).Hash.ToLowerInvariant()
$permAfter = (Get-FileHash -LiteralPath $perm -Algorithm SHA256).Hash.ToLowerInvariant()
if ($wadAfter -ne $wadBefore -or $permAfter -ne $permBefore) {
    throw 'Read-only resolver observed a game-file hash change. Refusing to publish.'
}

Write-Information -InformationAction Continue "Saved: $out"
Write-Information -InformationAction Continue 'No God of War files were modified.'

if ($NoPublish) { return }

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for HUD resource-chain report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive DockPoint HUD resource chain' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for HUD resource-chain report.' }
    } else {
        Write-Information -InformationAction Continue 'HUD resource-chain report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

git -C $repo push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw 'HUD resource-chain report push failed.' }
