param([string]$GameExe = 'G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe')
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (Test-Path (Join-Path $repo 'build\v0.10.3-lookup\active.json')) {
    throw 'Remove active probe before installer tests.'
}
$testRoot = Join-Path $repo ('build\v0.10.3-installer-tests\' + [Guid]::NewGuid().ToString('N'))
$target = Join-Path $testRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
# Local test fixture only. Never execute or commit this copy.
Copy-Item -LiteralPath $GameExe -Destination (Join-Path $testRoot 'GoW.exe')
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($target, "-- [CompletionistMap v0.10.1] test fixture`nMapOn = {}`nfunction MapOn:GetRealmMarkerInfo()`nend`n", $utf8)
$before = (Get-FileHash $target).Hash
$installer = Join-Path $PSScriptRoot 'lookup-probe.ps1'
& $installer -Mode Prepare -GameRoot $testRoot
if ((Get-FileHash $target).Hash -ne $before) { throw 'Prepare wrote target.' }
[IO.File]::WriteAllBytes((Join-Path $testRoot 'GoW.exe'), [byte[]]@(0))
$rejected = $false
try { & $installer -Mode Install -GameRoot $testRoot } catch { $rejected = $true }
if (-not $rejected -or (Get-FileHash $target).Hash -ne $before) { throw 'Unsupported executable accepted.' }
Copy-Item -LiteralPath $GameExe -Destination (Join-Path $testRoot 'GoW.exe')
& $installer -Mode Install -GameRoot $testRoot
$installed = [IO.File]::ReadAllBytes($target)
$rejected = $false
try { & $installer -Mode Install -GameRoot $testRoot } catch { $rejected = $true }
if (-not $rejected) { throw 'Duplicate install accepted.' }
[IO.File]::AppendAllText($target, "`n-- New user work`n", $utf8)
$changed = (Get-FileHash $target).Hash
$rejected = $false
try { & $installer -Mode Remove -GameRoot $testRoot } catch { $rejected = $true }
if (-not $rejected -or (Get-FileHash $target).Hash -ne $changed) { throw 'Rollback overwrote later work.' }
[IO.File]::WriteAllBytes($target, $installed)
& $installer -Mode Remove -GameRoot $testRoot
if ((Get-FileHash $target).Hash -ne $before) { throw 'Rollback changed original bytes.' }
Write-Host 'Installer tests passed: prepare no-write, executable guard, install, duplicate guard, later-edit guard, exact rollback.'
