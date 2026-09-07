param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $GameRoot)) { throw "God of War root not found: $GameRoot" }
if (Get-Process -Name 'GoW' -ErrorAction SilentlyContinue) {
    throw 'God of War is running. Close the game before removing the HUD texture proof.'
}

$packBase = '0Completionist_v102_hud_r3l3_raven'
$wadDir = Join-Path $GameRoot 'exec\wad\pc_le'
$pack = Join-Path $wadDir ($packBase + '.texpack')
$toc = Join-Path $wadDir ($packBase + '.texpack.toc')
$bootPath = Join-Path $GameRoot 'exec\boot-options.json'

if (Test-Path -LiteralPath $bootPath) {
    $boot = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
    $prop = $boot.PSObject.Properties['patch-texpacks']
    if ($null -ne $prop) {
        $boot.'patch-texpacks' = @($boot.'patch-texpacks' | Where-Object { [string]$_ -ne $packBase })
        $json = $boot | ConvertTo-Json -Depth 20
        $utf8NoBom = New-Object Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($bootPath, $json + [Environment]::NewLine, $utf8NoBom)
    }
}

Remove-Item -LiteralPath $pack -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $toc -Force -ErrorAction SilentlyContinue

Write-Host 'Removed v0.10.2 HUD R3_L3 Raven texture proof.'
Write-Host 'Other patch-texpack entries, including the map Raven proof, were preserved.'
