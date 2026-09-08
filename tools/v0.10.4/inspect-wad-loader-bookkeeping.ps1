param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$PythonModuleDir
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Wrong branch: $branch" }
if (-not $PythonModuleDir) { $PythonModuleDir = Join-Path $repo 'dist\re-tools' }
$python = Get-Command python -ErrorAction Stop
$report = Join-Path $repo 'archive\field-logs\completionist-v104-wad-loader-bookkeeping.json'
$toolArgs = @(
    (Join-Path $PSScriptRoot 'inspect-wad-loader-bookkeeping.py'),
    '--game-root', $GameRoot,
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
if ($LASTEXITCODE -ne 0) { throw 'WAD loader bookkeeping probe failed.' }

Write-Host ''
Write-Host 'WAD loader bookkeeping probe complete.'
Write-Host 'No game files or saves were modified. No runtime candidate was installed.'
Write-Host "Report: $report"
