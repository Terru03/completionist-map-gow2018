param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$PythonModuleDir,
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Wrong branch: $branch" }
if (-not $PythonModuleDir) { $PythonModuleDir = Join-Path $repo 'dist\re-tools' }
$python = Get-Command python -ErrorAction Stop
$reportRel = 'archive/field-logs/completionist-v104-wad-loader-bookkeeping.json'
$report = Join-Path $repo ($reportRel -replace '/', '\')

& $python (Join-Path $PSScriptRoot 'test_wad_loader_bookkeeping.py')
if ($LASTEXITCODE -ne 0) { throw 'WAD loader bookkeeping unit tests failed.' }

$toolArgs = @(
    (Join-Path $PSScriptRoot 'inspect-wad-loader-bookkeeping-v2.py'),
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

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for WAD bookkeeping report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive WAD loader bookkeeping probe' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for WAD bookkeeping report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for WAD bookkeeping report.' }
    } else {
        Write-Host 'WAD bookkeeping report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'WAD loader bookkeeping probe complete.'
Write-Host 'No game files or saves were modified. No runtime candidate was installed.'
Write-Host "Report: $report"
