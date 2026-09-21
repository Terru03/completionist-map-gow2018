param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo
if ((& git branch --show-current).Trim() -ne $ExpectedBranch) {
    throw "Need branch $ExpectedBranch."
}
if (@(& git status --porcelain --untracked-files=no).Count -gt 0) {
    throw 'Tracked tree must be clean before proof refresh.'
}

$prepare = Join-Path $repo 'tools\v0.10.5\prepare-all-ravens-delivery-candidate.py'
$proofRelative = 'archive/all-ravens/all-ravens-release-candidate-offline.json'
$proofPath = Join-Path $repo ($proofRelative -replace '/', [IO.Path]::DirectorySeparatorChar)
foreach ($required in @($prepare, $proofPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Need proof-refresh file: $required"
    }
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-delivery-proof-refresh-$stamp"
$outDir = Join-Path $repo ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$console = Join-Path $outDir 'console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
$errorFile = Join-Path $outDir 'error.txt'
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$transcript = $false
function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
}

function Invoke-PythonLogged([string[]]$Arguments) {
    $pythonExe = 'python.exe'
    $prefix = @()
    & py.exe -3.14 -c 'import sys' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonExe = 'py.exe'
        $prefix = @('-3.14')
    }
    $lines = @(& $pythonExe @prefix @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    $lines | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) {
        throw "Python command failed exit=$exitCode args=$($Arguments -join ' ')"
    }
}

function Publish-Evidence([string]$Message, [bool]$IncludeProof) {
    Stop-LocalTranscript
    if ($IncludeProof) {
        & git add -- $proofRelative
        if ($LASTEXITCODE -ne 0) { throw 'git add proof failed.' }
    }
    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add evidence failed.' }
    $commitPaths = @($relativeDir)
    if ($IncludeProof) { $commitPaths = @($proofRelative, $relativeDir) }
    & git commit -m $Message -- @commitPaths | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git commit evidence failed.' }
    & git push origin $ExpectedBranch | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git push evidence failed.' }
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true
    Write-Host 'RAVEN DELIVERY PROOF REFRESH - START'
    Write-Host "branch=$ExpectedBranch"

    Invoke-PythonLogged @($prepare, '--refresh-proof')
    Invoke-PythonLogged @($prepare, '--check')

    $changed = @(& git diff --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect proof-refresh diff.' }
    if ($changed.Count -ne 1 -or $changed[0] -ne $proofRelative) {
        Write-Host 'Unexpected tracked changes:'
        $changed | ForEach-Object { Write-Host $_ }
        throw 'Proof refresh changed an unexpected tracked path.'
    }

    $proof = Get-Content -LiteralPath $proofPath -Raw | ConvertFrom-Json
    $mapEntry = $proof.files.PSObject.Properties['mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua']
    if ($null -eq $mapEntry) { throw 'Refreshed proof misses mapmenu.lua.' }
    $mapSha = [string]$mapEntry.Value.sha256
    $mapBytes = [int64]$mapEntry.Value.bytes

    @(
        'result=RAVEN_DELIVERY_PROOF_REFRESH_PASSED'
        "timestamp=$(Get-Date -Format o)"
        "branch=$ExpectedBranch"
        "mapmenu_sha256=$mapSha"
        "mapmenu_bytes=$mapBytes"
        'source_game_rebuild=false'
        'non_map_candidate_pins_unchanged=true'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8

    Write-Host "RAVEN_DELIVERY_PROOF_REFRESH_PASSED mapmenu_sha256=$mapSha bytes=$mapBytes"
    Publish-Evidence 'build(v0.10.5): refresh Raven delivery proof after UI polish' $true
    Write-Host "Evidence pushed: $relativeDir"
}
catch {
    $outer = $_
    try { $outer.Exception.ToString() | Set-Content -LiteralPath $errorFile -Encoding UTF8 } catch {}
    try {
        & git restore --source=HEAD -- $proofRelative
        if ($LASTEXITCODE -ne 0) { Write-Host 'WARNING: could not restore proof after failure.' }
    } catch {}
    try {
        @(
            'result=RAVEN_DELIVERY_PROOF_REFRESH_FAILED'
            "timestamp=$(Get-Date -Format o)"
            "branch=$ExpectedBranch"
            "reason=$($outer.Exception.Message)"
        ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
    } catch {}
    Write-Host "RAVEN_DELIVERY_PROOF_REFRESH_FAILED: $($outer.Exception.Message)"
    try {
        Publish-Evidence "test(v0.10.5): archive Raven proof refresh failure $stamp" $false
        Write-Host "Failure evidence pushed: $relativeDir"
    } catch {
        Write-Host "FAILURE_EVIDENCE_PUSH_FAILED: $($_.Exception.Message)"
    }
    exit 1
}
finally {
    Stop-LocalTranscript
}
