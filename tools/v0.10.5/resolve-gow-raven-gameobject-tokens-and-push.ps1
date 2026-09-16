[CmdletBinding()]
param()

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
    if (-not $python) {
        throw 'python.exe was not found in PATH.'
    }

    Write-Host 'GoW.exe must be running and sitting at the main menu.'
    Write-Host 'No save loading or x64dbg steps are required; this calls the verified decoder directly.'

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $relativeDir = "archive/field-logs/runtime/raven-gameobject-token-resolver-$stamp"
    $relativeEvidence = "$relativeDir/raven-gameobject-token-resolver.json"
    $absoluteEvidence = Join-Path $RepoRoot ($relativeEvidence -replace '/', [IO.Path]::DirectorySeparatorChar)

    & $python.Source $Resolver --output $absoluteEvidence
    if ($LASTEXITCODE -ne 0) {
        throw "Raven resolver failed with exit code $LASTEXITCODE. Nothing was committed or pushed."
    }
    if (-not (Test-Path -LiteralPath $absoluteEvidence)) {
        throw "Resolver reported success but evidence file was not created: $absoluteEvidence"
    }

    & git add -- $relativeEvidence
    if ($LASTEXITCODE -ne 0) { throw 'git add of Raven evidence failed.' }

    # --only guarantees that unrelated staged/worktree changes are not included.
    & git commit --only -m $CommitMessage -- $relativeEvidence
    if ($LASTEXITCODE -ne 0) { throw 'git commit of Raven evidence failed.' }

    & git push origin $ExpectedBranch
    if ($LASTEXITCODE -ne 0) {
        throw 'git push failed. The evidence is committed locally and can be pushed later.'
    }

    $sha = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'git rev-parse HEAD failed after push.' }
    Write-Host ''
    Write-Host "PUSHED PASS: $sha"
    Write-Host "Evidence: $relativeEvidence"
}
finally {
    Pop-Location
}
