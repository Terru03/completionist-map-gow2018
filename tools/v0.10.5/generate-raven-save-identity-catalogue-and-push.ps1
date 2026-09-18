[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-collectibles-production-research'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Generator = Join-Path $PSScriptRoot 'generate-raven-save-identity-catalogue.py'
$Output = Join-Path $RepoRoot 'catalogue\odins-ravens-save-identities.json'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/source-scans/raven-save-identity-catalogue-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$evidence = Join-Path $outDir 'summary.json'
$console = Join-Path $outDir 'console-log.txt'

function Invoke-Git {
    param([Parameter(Mandatory=$true)][string[]]$GitArgs)
    & git -C $RepoRoot @GitArgs | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$branch = (& git -C $RepoRoot branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) { throw "Wrong branch '$branch'; expected '$ExpectedBranch'." }
if (-not (Test-Path -LiteralPath $Generator -PathType Leaf)) { throw "Missing generator: $Generator" }
if (-not (Test-Path -LiteralPath (Join-Path $GameRoot 'exec\wad\pc_le') -PathType Container)) {
    throw "God of War WAD root not found under: $GameRoot"
}
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Write-Host 'RAVEN SAVE IDENTITY CATALOGUE - STATIC'
Write-Host 'Derives all 53 identities from shipped WADs and verifies the frozen ravenKilled proof.'
Write-Host 'No game process and no save/progression writes.'
Write-Host ''

$lines = & $python.Source $Generator --game-root $GameRoot --output $Output --evidence-json $evidence 2>&1 |
    ForEach-Object { "$_"; Write-Host "$_" }
$exitCode = $LASTEXITCODE
$lines | Set-Content -LiteralPath $console -Encoding UTF8

if ($exitCode -ne 0) {
    Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 -Value "exit_code=$exitCode"
    Invoke-Git @('add','-f','--',$relativeDir)
    Invoke-Git @('commit','-m',"research(v0.10.5): archive failed Raven save identity catalogue $stamp",'--',$relativeDir)
    Invoke-Git @('push','origin',$ExpectedBranch)
    throw "Raven save identity catalogue generation failed; evidence was pushed."
}

$testLines = & $python.Source (Join-Path $PSScriptRoot 'test_raven_catalogue.py') 2>&1 |
    ForEach-Object { "$_"; Write-Host "$_" }
$testExit = $LASTEXITCODE
$testLines | Set-Content -LiteralPath (Join-Path $outDir 'catalogue-tests.txt') -Encoding UTF8
if ($testExit -ne 0) {
    throw "Raven catalogue tests failed after identity generation."
}

Invoke-Git @('add','-f','--','catalogue/odins-ravens-save-identities.json',$relativeDir)
Invoke-Git @('commit','-m',"research(v0.10.5): derive all Raven save identities $stamp",'--','catalogue/odins-ravens-save-identities.json',$relativeDir)
Invoke-Git @('push','origin',$ExpectedBranch)
$head = (& git -C $RepoRoot rev-parse HEAD).Trim()

Write-Host ''
Write-Host "RAVEN_SAVE_IDENTITY_CATALOGUE_PUSHED $head"
Write-Host "Evidence: $relativeDir"
