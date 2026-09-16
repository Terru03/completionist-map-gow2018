[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$ExpectedBranch = 'codex/all-collectibles-production-research'
$CommitMessage = 'research: capture Raven GameObject token mappings'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Resolver = Join-Path $PSScriptRoot 'resolve-gow-raven-gameobject-tokens.py'

Push-Location $RepoRoot
try {
    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'git branch --show-current failed.' }
    if ($branch -ne $ExpectedBranch) {
        throw "Wrong branch: '$branch'. Expected '$ExpectedBranch'."
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw 'python.exe was not found in PATH.' }

    Write-Host ''
    Write-Host 'This version passively captures GoW''s REAL decoder on the game thread.'
    Write-Host '1. Start GoW.'
    Write-Host '2. Run this command.'
    Write-Host '3. While it says WAITING, return to GoW and load/reload the Raven evidence save.'
    Write-Host 'No x64dbg is required. The temporary hook is removed automatically.'
    Write-Host ''

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $relativeDir = "archive/field-logs/runtime/raven-gameobject-token-resolver-$stamp"
    $relativeEvidence = "$relativeDir/raven-gameobject-token-resolver.json"
    $relativeLog = "$relativeDir/raven-gameobject-token-resolver.log"
    $absoluteEvidence = Join-Path $RepoRoot ($relativeEvidence -replace '/', [IO.Path]::DirectorySeparatorChar)
    $absoluteLog = Join-Path $RepoRoot ($relativeLog -replace '/', [IO.Path]::DirectorySeparatorChar)

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $absoluteLog) | Out-Null

    $lines = & $python.Source $Resolver --output $absoluteEvidence --timeout-seconds $TimeoutSeconds 2>&1 |
        ForEach-Object { "$_"; Write-Host "$_" }
    $exit = $LASTEXITCODE
    $lines | Set-Content -LiteralPath $absoluteLog -Encoding UTF8

    # Runtime logs are intentionally ignored globally; -f archives this one explicit evidence run.
    & git add -f -- $relativeLog
    if ($LASTEXITCODE -ne 0) { throw 'git add -f of Raven resolver log failed.' }

    if ($exit -eq 0) {
        if (-not (Test-Path -LiteralPath $absoluteEvidence)) {
            throw "Resolver reported success but evidence file was not created: $absoluteEvidence"
        }
        & git add -f -- $relativeEvidence
        if ($LASTEXITCODE -ne 0) { throw 'git add -f of Raven evidence failed.' }
    }

    $paths = @($relativeLog)
    if ($exit -eq 0) { $paths += $relativeEvidence }
    $commitMessage = if ($exit -eq 0) { $CommitMessage } else { 'research: archive failed Raven token capture' }

    & git commit --only -m $commitMessage -- $paths
    if ($LASTEXITCODE -ne 0) { throw 'git commit of Raven resolver output failed.' }

    & git push origin $ExpectedBranch
    if ($LASTEXITCODE -ne 0) {
        throw 'git push failed. The resolver output is committed locally and can be pushed later.'
    }

    $sha = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'git rev-parse HEAD failed after push.' }

    Write-Host ''
    if ($exit -eq 0) {
        Write-Host "PUSHED PASS: $sha"
        Write-Host "Evidence: $relativeEvidence"
    } else {
        Write-Host "PUSHED FAILURE LOG: $sha"
        Write-Host "Log: $relativeLog"
        throw "Raven resolver failed with exit code $exit, but the failure log WAS committed and pushed."
    }
}
finally {
    Pop-Location
}
