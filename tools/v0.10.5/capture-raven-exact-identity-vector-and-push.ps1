[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-collectibles-production-research'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Capture = Join-Path $PSScriptRoot 'capture-raven-exact-identity-vector.py'
$Catalogue = Join-Path $RepoRoot 'catalogue\odins-ravens.json'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-exact-identity-vector-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$outJson = Join-Path $outDir 'raven-exact-identity-vector.json'
$outText = Join-Path $outDir 'raven-exact-identity-vector.txt'
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
if (-not (Test-Path -LiteralPath $Capture -PathType Leaf)) { throw "Missing capture: $Capture" }
if (-not (Test-Path -LiteralPath $Catalogue -PathType Leaf)) { throw "Missing catalogue: $Catalogue" }
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Write-Host 'RAVEN EXACT IDENTITY VECTOR - READ ONLY'
Write-Host 'Keep God of War running in Veithurgard / VikingFuneral with the area fully loaded.'
Write-Host 'Uses ReadProcessMemory only. No debugger, process writes, save writes, or progression writes.'
Write-Host ''

$lines = & $python.Source $Capture --game-root $GameRoot --catalogue $Catalogue --output-json $outJson --output-text $outText 2>&1 |
    ForEach-Object { "$_"; Write-Host "$_" }
$exitCode = $LASTEXITCODE
$lines | Set-Content -LiteralPath $console -Encoding UTF8

if ($exitCode -ne 0) {
    Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 -Value "exit_code=$exitCode"
}

Invoke-Git @('add','-f','--',$relativeDir)
$message = if ($exitCode -eq 0) {
    "research(v0.10.5): capture exact Raven identity vector $stamp"
} else {
    "research(v0.10.5): archive failed exact Raven identity capture $stamp"
}
Invoke-Git @('commit','-m',$message,'--',$relativeDir)
Invoke-Git @('push','origin',$ExpectedBranch)
$head = (& git -C $RepoRoot rev-parse HEAD).Trim()

if ($exitCode -ne 0) {
    throw "Exact Raven identity-vector capture failed; evidence pushed in $head"
}

Write-Host ''
Write-Host "RAVEN_EXACT_IDENTITY_VECTOR_PUSHED $head"
Write-Host "Evidence: $relativeDir"
