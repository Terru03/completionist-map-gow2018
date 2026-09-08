param(
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Wrong branch: $branch" }

$reportRel = 'archive/field-logs/completionist-v104-wad-loader-bookkeeping.json'
$report = Join-Path $repo ($reportRel -replace '/', '\')
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw 'Bookkeeping report is missing. Re-run inspect-wad-loader-bookkeeping.ps1 instead.'
}

$obj = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($obj.result -ne 'READ_ONLY_WAD_LOADER_BOOKKEEPING_PROBE') {
    throw "Unexpected report result: $($obj.result)"
}
if ($obj.game_files_written -ne $false -or $obj.runtime_test_ready -ne $false) {
    throw 'Report safety/runtime flags are not the expected read-only values.'
}
$expected = @{
    'r_ui.wad' = '92294d218855ee4fbd06f66a2071f61c6b831240aaf41a59a3b7b8168c0f4b04'
    'wad_r_ui.dcb' = '21ec389426fb8b6a7f89c8fff6751522aa7ded13324e041b885dd7a490c2d14a'
    'mapmaster.dcb' = '1e076f7c5f0aea8d93ad72365bcaa267361503eee10fcdab0522c699b188508a'
    'GoW.exe' = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
}
foreach ($name in $expected.Keys) {
    $actual = [string]$obj.source_hashes.$name
    if ($actual -ne $expected[$name]) { throw "Source hash mismatch in report for $name" }
}
if ($obj.source_hashes_unchanged_after_scan -ne $true) {
    throw 'Report does not prove source hashes remained unchanged.'
}
if ($null -eq $obj.stock_wad_accounting -or $null -eq $obj.native_probe -or $null -eq $obj.gates) {
    throw 'Report is incomplete.'
}

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
        Write-Host 'WAD bookkeeping report is already tracked and unchanged.'
    }
}
finally { Pop-Location }

Write-Host 'Validated and published the existing read-only WAD bookkeeping report.'
