param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Wrong branch: $branch" }
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before running the offline Raven registered-class build.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$python = Get-Command python -ErrorAction Stop
$builder = Join-Path $PSScriptRoot 'build-raven-ui-registered-class.py'
$work = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.4\raven-ui-registered-class'
$reportRel = 'archive/field-logs/completionist-v104-raven-ui-registered-class.json'
$report = Join-Path $repo ($reportRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path $work, (Split-Path $report -Parent) | Out-Null

& $python.Source -m py_compile $builder
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed for registered Raven class builder.' }

& $python.Source $builder --game-root $GameRoot --work-dir $work --output $report
if ($LASTEXITCODE -ne 0) { throw 'Offline registered Raven class build failed.' }

$obj = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($obj.result -ne 'OFFLINE_RAVEN_UI_REGISTERED_CLASS_CANDIDATE_BUILT' -or
    $obj.game_files_written -ne $false -or
    $obj.save_files_written -ne $false -or
    $obj.runtime_test_ready -ne $false -or
    $obj.source_hashes_unchanged_after_build -ne $true) {
    throw 'Registered Raven class report failed safety/completeness validation.'
}
if ($obj.corrected_bookkeeping.physical_payload_delta -ne 8 -or
    $obj.corrected_bookkeeping.typed_total_delta -ne 6 -or
    $obj.corrected_bookkeeping.final_header_payload_name_consistent -ne $true) {
    throw 'Corrected Raven WAD bookkeeping did not prove the expected 8 physical / 6 typed delta and final-name repair.'
}
if ($obj.gates.serialized_type_cohorts_match_corrected_counts -ne $true -or
    $obj.gates.type_table_rebuilt_from_stock_plus_proven_deltas -ne $true -or
    $obj.gates.heap_and_root_totals_equal_type_row_sum -ne $true -or
    $obj.gates.dedicated_gopool_entry_built -ne $true -or
    $obj.gates.new_runtime_candidate_allowed -ne $false) {
    throw 'Registered Raven class static gates are not in the expected state.'
}

# Validate that GOWTool can parse the corrected candidate WAD far enough to list
# and extract textures.  This writes only to the local work directory.
$gowTool = Join-Path $env:LOCALAPPDATA 'CompletionistMap\tools\GOWTool-v0.1.3-alpha\GOWTool.exe'
$gowToolSha = 'C1B0F3C7FB9DD2B26AE7EF4AC377308761FD3C7AFB21DAC7E4BEE20160A0008B'
if (-not (Test-Path -LiteralPath $gowTool -PathType Leaf)) { throw "GOWTool missing: $gowTool" }
if ((Get-FileHash -LiteralPath $gowTool -Algorithm SHA256).Hash -ne $gowToolSha) {
    throw 'GOWTool SHA256 does not match the pinned v0.1.3-alpha binary.'
}
$candidateWad = [string]$obj.candidate.r_ui_wad.path
$parseDir = Join-Path $work 'gowtool-parse'
Remove-Item -LiteralPath $parseDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $parseDir | Out-Null
$toolDir = Split-Path -Parent $gowTool
Push-Location $toolDir
try {
    & $gowTool wad -p $candidateWad -o $parseDir -t -d
    $gowExit = $LASTEXITCODE
}
finally { Pop-Location }
if ($gowExit -ne 0) { throw "GOWTool rejected the corrected candidate WAD with exit code $gowExit." }

$obj | Add-Member -Force -NotePropertyName gowtool_parser_validation -NotePropertyValue ([pscustomobject]@{
    passed = $true
    exit_code = $gowExit
    output_directory = $parseDir
    pinned_gowtool_sha256 = $gowToolSha.ToLowerInvariant()
    game_files_written = $false
})
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($report, ($obj | ConvertTo-Json -Depth 40) + [Environment]::NewLine, $utf8NoBom)

# Reconfirm the pinned game sources were not touched.
$wadSource = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$dcbSource = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_ui.dcb'
if ((Get-FileHash -LiteralPath $wadSource -Algorithm SHA256).Hash -ne '92294D218855EE4FBD06F66A2071F61C6B831240AAF41A59A3B7B8168C0F4B04') {
    throw 'Game r_ui.wad changed during offline registered-class build.'
}
if ((Get-FileHash -LiteralPath $dcbSource -Algorithm SHA256).Hash -ne '21EC389426FB8B6A7F89C8FFF6751522AA7DED13324E041B885DD7A490C2D14A') {
    throw 'Game wad_r_ui.dcb changed during offline registered-class build.'
}

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for registered Raven class report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive corrected Raven registered-class build' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for registered Raven class report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for registered Raven class report.' }
    } else {
        Write-Host 'Registered Raven class report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Corrected Raven registered-class candidate built OFFLINE.'
Write-Host 'GOWTool parser validation passed.'
Write-Host 'No game files, saves, boot options, or progression state were modified.'
Write-Host "Report: $report"
