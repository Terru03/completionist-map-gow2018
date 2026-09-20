[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $RepoRoot

$Capture = Join-Path $RepoRoot 'tools\v0.10.5\capture-all-raven-gameobject-identities-readonly.py'
$Catalogue = Join-Path $RepoRoot 'catalogue\odins-ravens.json'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/all-raven-gameobject-identities-readonly-$stamp"
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
if ($branch -ne $ExpectedBranch) {
    throw "Wrong branch '$branch'; expected '$ExpectedBranch'."
}
$staged = @(& git -C $RepoRoot diff --cached --name-only)
if ($staged.Count -gt 0) {
    throw "Refusing pre-existing staged changes: $($staged -join ', ')"
}
foreach ($path in @($Capture, $Catalogue, (Join-Path $GameRoot 'GoW.exe'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}
$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') })
if ($running.Count -ne 1) {
    throw 'Start God of War and load the save you want to inspect before running this command.'
}
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Write-Host 'ALL RAVEN GAMEOBJECT IDENTITIES - READ ONLY'
Write-Host 'Keep God of War running on the loaded save. No gameplay action is required during the sweep.'
Write-Host 'Uses ReadProcessMemory only. No debugger, process writes, save reads/writes, or progression writes.'
Write-Host ''

$arguments = @(
    $Capture,
    '--game-root', $GameRoot,
    '--catalogue', $Catalogue,
    '--output-json', $outJson,
    '--output-text', $outText
)
$lines = & $python.Source @arguments 2>&1 | ForEach-Object { "$_"; Write-Host "$_" }
$exitCode = $LASTEXITCODE
$lines | Set-Content -LiteralPath $console -Encoding UTF8

if ($exitCode -ne 0) {
    Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 -Value "exit_code=$exitCode"
}

Invoke-Git @('add','-f','--',$relativeDir)
$message = if ($exitCode -eq 0) {
    "research(v0.10.5): capture all Raven GameObject identities read-only $stamp"
} else {
    "research(v0.10.5): archive failed all Raven identity sweep $stamp"
}
Invoke-Git @('commit','-m',$message,'--',$relativeDir)
Invoke-Git @('push','origin',$ExpectedBranch)
$head = (& git -C $RepoRoot rev-parse HEAD).Trim()

if ($exitCode -ne 0) {
    throw "Read-only all-Raven identity sweep failed; evidence pushed in $head"
}

Write-Host ''
Write-Host "ALL_RAVEN_GAMEOBJECT_IDENTITIES_READONLY_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
