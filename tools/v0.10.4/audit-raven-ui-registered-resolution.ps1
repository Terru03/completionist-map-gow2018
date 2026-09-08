param(
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Wrong branch: $branch" }
$python = Get-Command python -ErrorAction Stop

$candidateDir = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.4\raven-ui-registered-class'
$buildRel = 'archive/field-logs/completionist-v104-raven-ui-registered-class.json'
$outRel = 'archive/field-logs/completionist-v104-raven-ui-registered-resolution.json'
$buildReport = Join-Path $repo ($buildRel -replace '/', '\')
$out = Join-Path $repo ($outRel -replace '/', '\')
$script = Join-Path $PSScriptRoot 'audit-raven-ui-registered-resolution.py'

foreach ($required in @($script, $buildReport, (Join-Path $candidateDir 'r_ui.wad'), (Join-Path $candidateDir 'wad_r_ui.dcb'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}

& $python.Source -m py_compile $script
if ($LASTEXITCODE -ne 0) { throw 'Static Raven resolution audit syntax check failed.' }

& $python.Source $script `
    --candidate-dir $candidateDir `
    --build-report $buildReport `
    --output $out
if ($LASTEXITCODE -ne 0) { throw 'Static Raven resource-resolution audit failed.' }

$obj = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ($obj.result -ne 'STATIC_RAVEN_REGISTERED_CLASS_RESOLUTION_PROVED' -or
    $obj.game_files_written -ne $false -or
    $obj.save_files_written -ne $false -or
    $obj.static_resolution_gate_passed -ne $true -or
    $obj.runtime_test_ready -ne $true) {
    throw 'Static Raven resolution report failed completeness/safety validation.'
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for Raven resolution report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven registered-class resolution proof' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for Raven resolution report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for Raven resolution report.' }
    } else {
        Write-Host 'Raven resolution report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host ''
Write-Host 'Static Raven registered-class resolution gate passed.'
Write-Host 'The corrected candidate is now eligible for a reversible one-Raven runtime field proof.'
Write-Host 'No game files, saves, boot options, or progression state were modified.'
Write-Host "Report: $out"
