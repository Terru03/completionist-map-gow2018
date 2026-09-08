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
$focusRel = 'archive/field-logs/completionist-v104-wad-loader-focus.json'
$typeRel = 'archive/field-logs/completionist-v104-wad-type-signatures.json'
$focusReport = Join-Path $repo ($focusRel -replace '/', '\')
$typeReport = Join-Path $repo ($typeRel -replace '/', '\')
$ruiWad = Join-Path ([IO.Path]::GetFullPath($GameRoot)) 'exec\wad\pc_le\r_ui.wad'

$focusArgs = @(
    (Join-Path $PSScriptRoot 'inspect-wad-loader-focus.py'),
    '--game-root', $GameRoot,
    '--python-module-dir', $PythonModuleDir,
    '--output', $focusReport
)
& $python @focusArgs
if ($LASTEXITCODE -ne 0) { throw 'Focused WAD loader disassembly probe failed.' }

$typeArgs = @(
    (Join-Path $PSScriptRoot 'inspect-wad-type-signatures.py'),
    '--r-ui-wad', $ruiWad,
    '--output', $typeReport
)
& $python @typeArgs
if ($LASTEXITCODE -ne 0) { throw 'WAD type-signature probe failed.' }

$focus = Get-Content -LiteralPath $focusReport -Raw | ConvertFrom-Json
if ($focus.result -ne 'READ_ONLY_WAD_LOADER_FOCUS_DISASSEMBLY' -or
    $focus.game_files_written -ne $false -or
    $focus.save_files_written -ne $false -or
    $focus.runtime_test_ready -ne $false -or
    $focus.source_hash_unchanged_after_scan -ne $true) {
    throw 'Focused WAD loader report failed safety/completeness validation.'
}
$type = Get-Content -LiteralPath $typeReport -Raw | ConvertFrom-Json
if ($type.result -ne 'READ_ONLY_WAD_TYPE_SIGNATURE_CORRELATION' -or
    $type.game_files_written -ne $false -or
    $type.runtime_test_ready -ne $false -or
    $type.source_hash_unchanged_after_scan -ne $true) {
    throw 'WAD type-signature report failed safety/completeness validation.'
}

Push-Location $repo
try {
    git add -- $focusRel $typeRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for focused WAD reports.' }
    git diff --cached --check -- $focusRel $typeRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $focusRel $typeRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive focused WAD loader evidence' -- $focusRel $typeRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for focused WAD reports.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for focused WAD reports.' }
    } else {
        Write-Host 'Focused WAD reports unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Focused WAD loader and type-signature probes complete.'
Write-Host 'No game files, saves, boot options, or progression state were modified.'
Write-Host "Disassembly report: $focusReport"
Write-Host "Type report:        $typeReport"
