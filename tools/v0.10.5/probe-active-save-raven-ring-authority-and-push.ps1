[CmdletBinding()]
param(
    [string]$SaveRoot = "$HOME\Saved Games\God of War"
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-collectibles-production-research'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Probe = Join-Path $PSScriptRoot 'probe-active-save-raven-ring-authority.py'
$Identities = Join-Path $RepoRoot 'catalogue\odins-ravens-save-identities.json'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/save-forensics/active-raven-ring-authority-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$outJson = Join-Path $outDir 'report.json'
$outText = Join-Path $outDir 'report.txt'
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
if (-not (Test-Path -LiteralPath $Probe -PathType Leaf)) { throw "Missing probe: $Probe" }
if (-not (Test-Path -LiteralPath $Identities -PathType Leaf)) { throw "Missing identity catalogue: $Identities" }
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Write-Host 'ACTIVE SAVE RAVEN RING AUTHORITY - READ ONLY'
Write-Host 'Reads game.sav only, verifies its SHA-256 is unchanged, and writes evidence only into this Git repo.'
Write-Host ''

$lines = & $python.Source $Probe --save-root $SaveRoot --identities $Identities --output-json $outJson --output-text $outText 2>&1 |
    ForEach-Object { "$_"; Write-Host "$_" }
$exitCode = $LASTEXITCODE
$lines | Set-Content -LiteralPath $console -Encoding UTF8

if ($exitCode -ne 0) {
    Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 -Value "exit_code=$exitCode"
}

Invoke-Git @('add','-f','--',$relativeDir)
$message = if ($exitCode -eq 0) {
    "research(v0.10.5): probe active Raven save-ring authority $stamp"
} else {
    "research(v0.10.5): archive failed Raven save-ring authority probe $stamp"
}
Invoke-Git @('commit','-m',$message,'--',$relativeDir)
Invoke-Git @('push','origin',$ExpectedBranch)
$head = (& git -C $RepoRoot rev-parse HEAD).Trim()

if ($exitCode -ne 0) {
    throw "Active-save Raven ring authority probe failed; evidence pushed in $head"
}

Write-Host ''
Write-Host "ACTIVE_RAVEN_RING_AUTHORITY_PUSHED $head"
Write-Host "Evidence: $relativeDir"
