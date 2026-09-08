param([string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar')

$ErrorActionPreference = 'Stop'
$python = Get-Command python -ErrorAction Stop
& $python.Source (Join-Path $PSScriptRoot 'inspect-compass-hud-physical-groups.py') --game-root $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Physical HUD group inspection failed.' }
