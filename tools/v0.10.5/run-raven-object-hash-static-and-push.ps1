[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$analyzer = Join-Path $PSScriptRoot 'analyze-raven-object-hash-static.py'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/source-scans/raven-object-hash-static-$stamp"
$outDir = Join-Path $repo ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$jsonPath = Join-Path $outDir 'raven-object-hash-static.json'
$logPath = Join-Path $outDir 'console-log.txt'
$resultPath = Join-Path $outDir 'result.txt'

function Invoke-Git {
    param([Parameter(Mandatory=$true)][string[]]$GitArgs)
    & git -C $repo @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$currentBranch = (& git -C $repo branch --show-current).Trim()
if ($currentBranch -ne $expectedBranch) {
    throw "Wrong branch: '$currentBranch'. Expected '$expectedBranch'."
}
if (-not (Test-Path -LiteralPath $analyzer -PathType Leaf)) {
    throw "Missing analyzer: $analyzer"
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "Game root missing: $GameRoot"
}

$python = Get-Command python -ErrorAction Stop
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$lines = & $python.Source $analyzer --game-root $GameRoot --output $jsonPath 2>&1 |
    ForEach-Object { "$_"; Write-Host "$_" }
$exit = $LASTEXITCODE
$lines | Set-Content -LiteralPath $logPath -Encoding UTF8

if (Test-Path -LiteralPath $jsonPath -PathType Leaf) {
    $json = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json
    @(
        "result=$($json.result)"
        "common_recipe_matches=$(@($json.common_recipe_matches).Count)"
        "wad=$($json.wad)"
        "read_only=$($json.read_only)"
        "save_or_progression_written=$($json.save_or_progression_written)"
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
}
else {
    @(
        'result=ANALYZER_FAILED_BEFORE_JSON'
        "exit_code=$exit"
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
}

Invoke-Git @('add','--',$relativeDir)
$message = if ($exit -eq 0) {
    "research(v0.10.5): archive Raven object-hash static analysis $stamp"
}
else {
    "research(v0.10.5): archive failed Raven object-hash static analysis $stamp"
}
Invoke-Git @('commit','-m',$message,'--',$relativeDir)
Invoke-Git @('push','origin',$expectedBranch)

$head = (& git -C $repo rev-parse HEAD).Trim()
if ($exit -ne 0) {
    throw "Analyzer failed with exit code $exit; failure evidence pushed in $head"
}

Write-Host "RAVEN_OBJECT_HASH_STATIC_ANALYSIS_PUSHED $head"
