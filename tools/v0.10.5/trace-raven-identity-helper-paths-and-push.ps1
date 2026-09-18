[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-collectibles-production-research'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Tracer = Join-Path $PSScriptRoot 'trace-raven-identity-helper-paths.py'
$Catalogue = Join-Path $RepoRoot 'catalogue\odins-ravens.json'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/source-scans/raven-identity-helper-paths-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$outJson = Join-Path $outDir 'raven-identity-helper-paths.json'
$outText = Join-Path $outDir 'raven-identity-helper-paths.txt'
$console = Join-Path $outDir 'console-log.txt'

function Invoke-Git {
    param([Parameter(Mandatory=$true)][string[]]$GitArgs)
    & git -C $RepoRoot @GitArgs | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$branch = (& git -C $RepoRoot branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    throw "Wrong branch '$branch'; expected '$ExpectedBranch'."
}
if (-not (Test-Path -LiteralPath $Tracer -PathType Leaf)) { throw "Missing tracer: $Tracer" }
if (-not (Test-Path -LiteralPath $Catalogue -PathType Leaf)) { throw "Missing catalogue: $Catalogue" }
if (-not (Test-Path -LiteralPath (Join-Path $GameRoot 'GoW.exe') -PathType Leaf)) {
    throw "GoW.exe not found under: $GameRoot"
}
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Write-Host 'RAVEN IDENTITY HELPER PATH TRACE'
Write-Host 'Static analysis always runs. If GoW is already running, a small read-only metadata sample is added.'
Write-Host 'No debugger, no process writes, no save/progression writes.'
Write-Host ''

$lines = & $python.Source $Tracer --game-root $GameRoot --catalogue $Catalogue --output-json $outJson --output-text $outText 2>&1 |
    ForEach-Object { "$_"; Write-Host "$_" }
$exitCode = $LASTEXITCODE
$lines | Set-Content -LiteralPath $console -Encoding UTF8

if ($exitCode -ne 0) {
    Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 -Value "exit_code=$exitCode"
}

Invoke-Git @('add','-f','--',$relativeDir)
$message = if ($exitCode -eq 0) {
    "research(v0.10.5): trace Raven identity helper paths $stamp"
} else {
    "research(v0.10.5): archive failed Raven identity helper trace $stamp"
}
Invoke-Git @('commit','-m',$message,'--',$relativeDir)
Invoke-Git @('push','origin',$ExpectedBranch)
$head = (& git -C $RepoRoot rev-parse HEAD).Trim()

if ($exitCode -ne 0) {
    throw "Raven identity helper trace failed; evidence pushed in $head"
}

Write-Host ''
Write-Host "RAVEN_IDENTITY_HELPER_TRACE_PUSHED $head"
Write-Host "Evidence: $relativeDir"
