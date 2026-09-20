[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $RepoRoot

$Probe = Join-Path $RepoRoot 'tools\v0.10.5\probe-active-save-raven-ring-authority.py'
$Identities = Join-Path $RepoRoot 'catalogue\odins-ravens-gameobject-identities.json'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/save-forensics/active-raven-ring-authority-53-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$outJson = Join-Path $outDir 'report.json'
$outText = Join-Path $outDir 'report.txt'
$console = Join-Path $outDir 'console-log.txt'

function Invoke-Git {
    param([Parameter(Mandatory=$true)][string[]]$GitArgs)
    & git -C $RepoRoot @GitArgs | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE" }
}

$branch = (& git -C $RepoRoot branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) { throw "Wrong branch '$branch'; expected '$ExpectedBranch'." }
$staged = @(& git -C $RepoRoot diff --cached --name-only)
if ($staged.Count -gt 0) { throw "Refusing pre-existing staged changes: $($staged -join ', ')" }
foreach ($path in @($Probe, $Identities)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required file: $path" }
}
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War before this read-only save scan so the active save cannot change mid-read.'
}
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Write-Host 'ACTIVE SAVE RAVEN RING AUTHORITY - 53 IDENTITIES - READ ONLY'
Write-Host 'God of War must remain closed while this runs.'
Write-Host 'The script reads game.sav only and verifies its SHA-256 is unchanged.'
Write-Host ''

$arguments = @($Probe, '--identities', $Identities, '--output-json', $outJson, '--output-text', $outText)
$lines = & $python.Source @arguments 2>&1 | ForEach-Object { "$_"; Write-Host "$_" }
$exitCode = $LASTEXITCODE
$lines | Set-Content -LiteralPath $console -Encoding UTF8

if ($exitCode -ne 0) { Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 -Value "exit_code=$exitCode" }

Invoke-Git @('add','-f','--',$relativeDir)
$message = if ($exitCode -eq 0) { "research(v0.10.5): scan active save Raven authority with 53 identities $stamp" } else { "research(v0.10.5): archive failed 53-Raven authority scan $stamp" }
Invoke-Git @('commit','-m',$message,'--',$relativeDir)
Invoke-Git @('push','origin',$ExpectedBranch)
$head = (& git -C $RepoRoot rev-parse HEAD).Trim()

if ($exitCode -ne 0) { throw "53-Raven active-save authority scan failed; evidence pushed in $head" }

Write-Host ''
Write-Host "ACTIVE_SAVE_RAVEN_RING_AUTHORITY_53_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
