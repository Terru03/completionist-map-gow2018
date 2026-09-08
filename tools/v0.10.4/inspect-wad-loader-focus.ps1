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
$reportRel = 'archive/field-logs/completionist-v104-wad-loader-focus.json'
$report = Join-Path $repo ($reportRel -replace '/', '\')

$toolArgs = @(
    (Join-Path $PSScriptRoot 'inspect-wad-loader-focus.py'),
    '--game-root', $GameRoot,
    '--python-module-dir', $PythonModuleDir,
    '--output', $report
)
& $python @toolArgs
if ($LASTEXITCODE -ne 0) { throw 'Focused WAD loader probe failed.' }

$obj = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($obj.result -ne 'READ_ONLY_WAD_LOADER_FOCUS_DISASSEMBLY' -or
    $obj.game_files_written -ne $false -or
    $obj.save_files_written -ne $false -or
    $obj.runtime_test_ready -ne $false -or
    $obj.source_hash_unchanged_after_scan -ne $true) {
    throw 'Focused WAD loader report failed safety/completeness validation.'
}

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for focused WAD loader report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive focused WAD loader probe' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for focused WAD loader report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for focused WAD loader report.' }
    } else {
        Write-Host 'Focused WAD loader report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Focused WAD loader probe complete.'
Write-Host 'No game files, saves, boot options, or progression state were modified.'
Write-Host "Report: $report"
