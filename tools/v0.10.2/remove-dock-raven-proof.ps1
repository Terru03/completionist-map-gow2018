param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $GameRoot)) { throw "God of War root not found: $GameRoot" }
if (Get-Process -Name 'GoW' -ErrorAction SilentlyContinue) {
    throw 'God of War is running. Close the game before removing the texture proof.'
}

$patchEntry = '../../patch/pc_le/completionist_v102_dock_raven'
$patchDir = Join-Path $GameRoot 'exec\patch\pc_le'
$pack = Join-Path $patchDir 'completionist_v102_dock_raven.texpack'
$toc = Join-Path $patchDir 'completionist_v102_dock_raven.texpack.toc'
$bootPath = Join-Path $GameRoot 'exec\boot-options.json'

if (Test-Path -LiteralPath $bootPath) {
    $boot = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
    $prop = $boot.PSObject.Properties['patch-texpacks']
    if ($null -ne $prop) {
        $boot.'patch-texpacks' = @($boot.'patch-texpacks' | Where-Object { [string]$_ -ne $patchEntry })
        $json = $boot | ConvertTo-Json -Depth 20
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($bootPath, $json + [Environment]::NewLine, $utf8NoBom)
    }
}

Remove-Item -LiteralPath $pack -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $toc -Force -ErrorAction SilentlyContinue

Write-Host 'Removed v0.10.2 DockPoint Raven texture proof.'
Write-Host 'Other patch-texpack entries were preserved.'
