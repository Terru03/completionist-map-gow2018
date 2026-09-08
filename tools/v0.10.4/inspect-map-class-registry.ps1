param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$LuaRoot,
    [string]$PythonModuleDir
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Wrong branch: $branch" }
if (-not $LuaRoot) { $LuaRoot = Join-Path $repo 'dist\gowlua-src' }
if (-not $PythonModuleDir) { $PythonModuleDir = Join-Path $repo 'dist\re-tools' }
$python = Get-Command python -ErrorAction Stop
$report = Join-Path $repo 'archive\field-logs\completionist-v104-map-class-registry.json'
$toolArgs = @(
    (Join-Path $PSScriptRoot 'inspect-map-class-registry.py'),
    '--game-root', $GameRoot,
    '--lua-root', $LuaRoot,
    '--python-module-dir', $PythonModuleDir,
    '--output', $report
)
foreach ($label in @('raven-ui-logical-clone', 'raven-ui-visual-clone')) {
    $candidate = Join-Path $env:LOCALAPPDATA "CompletionistMap\work\v0.10.4\$label\r_ui.wad"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $toolArgs += @('--candidate-wad', $candidate)
    }
}
& $python @toolArgs
if ($LASTEXITCODE -ne 0) { throw 'Registry scan failed. No runtime proof ready.' }
Write-Host 'Read-only scan done. No game or save writes. No runtime test ready.'
