[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ExpectedBranch = 'codex/all-collectibles-production-research'
$SuccessCommitMessage = 'research: capture Raven GameObject token mappings'
$FailureCommitMessage = 'research: archive failed Raven token resolver run'

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

    Write-Host 'GoW.exe must be running with an actual save fully loaded into gameplay.'
    Write-Host 'Stand in the world, open the pause/options menu, then run this command.'
    Write-Host 'Do NOT leave the game at the title/main menu: the GameObject registry is not populated there.'
    Write-Host 'No x64dbg steps are required; this calls the verified decoder directly.'
    Write-Host ''

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $relativeDir = "archive/field-logs/runtime/raven-gameobject-token-resolver-$stamp"
    $relativeEvidence = "$relativeDir/raven-gameobject-token-resolver.json"
    $relativeLog = "$relativeDir/raven-gameobject-token-resolver.log"
    $absoluteDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
    $absoluteEvidence = Join-Path $RepoRoot ($relativeEvidence -replace '/', [IO.Path]::DirectorySeparatorChar)
    $absoluteLog = Join-Path $RepoRoot ($relativeLog -replace '/', [IO.Path]::DirectorySeparatorChar)

    New-Item -ItemType Directory -Force -Path $absoluteDir | Out-Null

    & $python.Source $Resolver --output $absoluteEvidence 2>&1 | Tee-Object -FilePath $absoluteLog
    $resolverExit = $LASTEXITCODE

    $commitPaths = @($relativeLog)
    if (Test-Path -LiteralPath $absoluteEvidence) {
        $commitPaths += $relativeEvidence
    }

    & git add -- $commitPaths
    if ($LASTEXITCODE -ne 0) { throw 'git add of Raven resolver output failed.' }

    if ($resolverExit -eq 0) {
        if (-not (Test-Path -LiteralPath $absoluteEvidence)) {
            throw "Resolver reported success but evidence file was not created: $absoluteEvidence"
        }
        $commitMessage = $SuccessCommitMessage
    }
    else {
        $commitMessage = $FailureCommitMessage
    }

    # --only guarantees that unrelated staged/worktree changes are not included.
    & git commit --only -m $commitMessage -- $commitPaths
    if ($LASTEXITCODE -ne 0) { throw 'git commit of Raven resolver output failed.' }

    & git push origin $ExpectedBranch
    if ($LASTEXITCODE -ne 0) {
        throw 'git push failed. The resolver output is committed locally and can be pushed later.'
    }

    $sha = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'git rev-parse HEAD failed after push.' }
    Write-Host ''

    if ($resolverExit -eq 0) {
        Write-Host "PUSHED PASS: $sha"
        Write-Host "Evidence: $relativeEvidence"
        Write-Host "Log:      $relativeLog"
        exit 0
    }

    Write-Host "PUSHED FAILURE EVIDENCE: $sha"
    Write-Host "Log: $relativeLog"
    throw "Raven resolver failed with exit code $resolverExit, but the failure log was committed and pushed for inspection."
}
finally {
    Pop-Location
}
