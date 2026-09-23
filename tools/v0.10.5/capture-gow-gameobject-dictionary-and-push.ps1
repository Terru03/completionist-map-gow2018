[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ExpectedBranch = 'codex/collectible-ship-heads'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Capture = Join-Path $PSScriptRoot 'capture-gow-gameobject-dictionary.py'

Push-Location $RepoRoot
try {
    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'git branch --show-current failed.' }
    if ($branch -ne $ExpectedBranch) {
        throw "Wrong branch: '$branch'. Expected '$ExpectedBranch'."
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw 'python.exe was not found in PATH.' }

    & $python.Source $Capture --self-test
    if ($LASTEXITCODE -ne 0) { throw 'GameObject dictionary capture self-test failed.' }

    Write-Host ''
    Write-Host 'FULL GAMEOBJECT DICTIONARY CAPTURE'
    Write-Host 'Start GoW and leave it at the title/main menu BEFORE loading the save you want to scan.'
    Write-Host 'This is intentionally NOT Raven-only: it records every successful hash-backed GameObject decode.'
    Write-Host 'After the hook says ARMED, load/reload your most complete saves and visit/reload relevant areas.'
    Write-Host 'When done, Alt-Tab back here and press ENTER. The hook will be removed before anything is pushed.'
    Write-Host ''

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $relativeDir = "archive/field-logs/runtime/gameobject-dictionary-capture-$stamp"
    $relativeJson = "$relativeDir/gameobject-dictionary.json"
    $relativeTsv = "$relativeDir/gameobject-dictionary.tsv"
    $relativeTranscript = "$relativeDir/capture-transcript.txt"
    $absoluteDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
    $absoluteJson = Join-Path $RepoRoot ($relativeJson -replace '/', [IO.Path]::DirectorySeparatorChar)
    $absoluteTsv = Join-Path $RepoRoot ($relativeTsv -replace '/', [IO.Path]::DirectorySeparatorChar)
    $absoluteTranscript = Join-Path $RepoRoot ($relativeTranscript -replace '/', [IO.Path]::DirectorySeparatorChar)
    New-Item -ItemType Directory -Path $absoluteDir -Force | Out-Null

    $captureCode = 1
    Start-Transcript -Path $absoluteTranscript -Force | Out-Null
    try {
        & $python.Source $Capture --output-json $absoluteJson --output-tsv $absoluteTsv
        $captureCode = $LASTEXITCODE
    }
    finally {
        Stop-Transcript | Out-Null
    }

    if ($captureCode -eq 0) {
        $commitMessage = 'research: capture full GameObject decode dictionary'
        $status = 'PASS'
    }
    else {
        $commitMessage = 'research: archive failed full GameObject dictionary capture'
        $status = "FAIL exit=$captureCode"
        Set-Content -LiteralPath (Join-Path $absoluteDir 'capture-failure.txt') -Encoding UTF8 -Value @(
            "status=$status"
            "captured_local=$(Get-Date -Format o)"
            'See capture-transcript.txt for the console transcript.'
        )
    }

    # Runtime evidence is ignored by default; force-add only this capture directory.
    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add of GameObject dictionary capture failed.' }

    & git commit --only -m $commitMessage -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git commit of GameObject dictionary capture failed.' }

    & git push origin $ExpectedBranch
    if ($LASTEXITCODE -ne 0) {
        throw 'git push failed. The capture is committed locally and can be pushed later.'
    }

    $sha = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'git rev-parse HEAD failed after push.' }
    Write-Host ''
    Write-Host "PUSHED ${status}: $sha"
    Write-Host "Capture: $relativeDir"

    if ($captureCode -ne 0) {
        throw "GameObject dictionary capture failed with exit code $captureCode, but the failure evidence WAS committed and pushed."
    }
}
finally {
    Pop-Location
}
