param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('v0.1-test','v0.2-diagnostic','v0.3-diagnostic','v0.3.1-diagnostic','v0.4-diagnostic','v0.5-raven-registry')]
    [string]$Version,

    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent

$relativeSource = switch ($Version) {
    'v0.5-raven-registry' { 'gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua' }
    default { 'gameart\ui\scripts\inworldmenu\mapmenu.lua' }
}

$source = Join-Path $GameRoot ('mods\lua_source\' + $relativeSource)
$out = Join-Path $repoRoot ('build\' + $relativeSource)
$patch = Join-Path $repoRoot "patches\$Version.patch"

if (-not (Test-Path $source)) { throw "Missing source file: $source" }
if (-not (Test-Path $patch)) { throw "Missing patch: $patch" }

$buildRoot = Join-Path $repoRoot 'build'
if (Test-Path $buildRoot) { Remove-Item $buildRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null
Copy-Item $source $out

Push-Location $buildRoot
try {
    # Loader-provided source may use CRLF while repository patches use LF.
    git apply --unsafe-paths --ignore-whitespace $patch
}
finally {
    Pop-Location
}

Write-Host "Built $Version -> $out"
