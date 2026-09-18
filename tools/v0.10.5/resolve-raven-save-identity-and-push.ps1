[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$static = Join-Path $PSScriptRoot 'analyze-raven-object-hash-static.py'
$liveReader = Join-Path $PSScriptRoot 'read-raven-gameobject-identity-memory.py'
$catalogue = Join-Path $repo 'catalogue\odins-ravens.json'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-save-identity-resolution-$stamp"
$outDir = Join-Path $repo ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$staticJson = Join-Path $outDir 'static-analysis.json'
$staticLog = Join-Path $outDir 'static-analysis.log'
$liveJson = Join-Path $outDir 'live-memory-identity.json'
$liveLog = Join-Path $outDir 'live-memory-identity.log'
$resultJson = Join-Path $outDir 'result.json'

function Invoke-Git {
    param([Parameter(Mandatory=$true)][string[]]$GitArgs)
    & git -C $repo @GitArgs | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Get-Python {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $python) { return @($python.Source) }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) { return @($py.Source, '-3') }
    throw 'Python 3 not found in PATH.'
}

function Invoke-PythonLogged {
    param(
        [string[]]$PythonPrefix,
        [string]$Script,
        [string[]]$Arguments,
        [string]$Log
    )
    $exe = $PythonPrefix[0]
    $prefixArgs = @()
    if ($PythonPrefix.Count -gt 1) {
        $prefixArgs = @($PythonPrefix[1..($PythonPrefix.Count - 1)])
    }
    $lines = & $exe @prefixArgs $Script @Arguments 2>&1 | ForEach-Object { "$_"; Write-Host "$_" }
    $exit = $LASTEXITCODE
    $lines | Set-Content -LiteralPath $Log -Encoding UTF8
    return $exit
}

function Push-Evidence {
    param([string]$Message)
    Invoke-Git @('add','--',$relativeDir)
    Invoke-Git @('commit','-m',$Message,'--',$relativeDir)
    Invoke-Git @('push','origin',$expectedBranch)
    return (& git -C $repo rev-parse HEAD).Trim()
}

$currentBranch = (& git -C $repo branch --show-current).Trim()
if ($currentBranch -ne $expectedBranch) {
    throw "Wrong branch '$currentBranch'; expected '$expectedBranch'."
}
foreach ($path in @($static,$liveReader,$catalogue)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required file: $path" }
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "Game root missing: $GameRoot"
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$python = @(Get-Python)

Write-Host 'RAVEN_SAVE_IDENTITY_RESOLUTION'
Write-Host '  stage 1: exhaustive static authored-identity search (through 6 elements)'
$staticExit = Invoke-PythonLogged -PythonPrefix $python -Script $static -Arguments @('--game-root',$GameRoot,'--max-recipe-length','6','--output',$staticJson) -Log $staticLog

if ($staticExit -ne 0 -or -not (Test-Path -LiteralPath $staticJson -PathType Leaf)) {
    $result = [ordered]@{
        schema = 1
        captured_utc = (Get-Date).ToUniversalTime().ToString('o')
        result = 'STATIC_ANALYSIS_FAILED'
        static_exit_code = $staticExit
        vector_capture_attempted = $false
        save_or_progression_written_by_probe = $false
    }
    [IO.File]::WriteAllText($resultJson,(($result | ConvertTo-Json -Depth 8) + [Environment]::NewLine),(New-Object Text.UTF8Encoding($false)))
    $head = Push-Evidence "research(v0.10.5): archive failed Raven save-identity resolution $stamp"
    throw "Static identity analysis failed; evidence pushed in $head"
}

$staticResult = Get-Content -LiteralPath $staticJson -Raw | ConvertFrom-Json
if ($staticResult.result -eq 'STATIC_RAVEN_OBJECT_HASH_RECIPE_FOUND') {
    $result = [ordered]@{
        schema = 1
        captured_utc = (Get-Date).ToUniversalTime().ToString('o')
        result = 'STATIC_IDENTITY_RECIPE_FOUND'
        recipes = @($staticResult.common_recipe_matches)
        vector_capture_attempted = $false
        save_or_progression_written_by_probe = $false
    }
    [IO.File]::WriteAllText($resultJson,(($result | ConvertTo-Json -Depth 12) + [Environment]::NewLine),(New-Object Text.UTF8Encoding($false)))
    $head = Push-Evidence "research(v0.10.5): resolve Raven save identity statically $stamp"
    Write-Host "RAVEN_SAVE_IDENTITY_STATIC_RESOLVED $head"
    exit 0
}

Write-Host '  static result: no authored identity recipe through 6 elements'
Write-Host '  stage 2: read-only live GameObject identity inspection'
$gow = @(
    Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }
)
if ($gow.Count -eq 0) {
    $result = [ordered]@{
        schema = 1
        captured_utc = (Get-Date).ToUniversalTime().ToString('o')
        result = 'STATIC_NOT_FOUND_GAME_NOT_RUNNING'
        static_result = $staticResult.result
        live_memory_attempted = $false
        instruction = 'Launch God of War, load VikingFuneral/Veithurgard so the three known Raven GameObjects are resident, then rerun this script.'
        save_or_progression_written_by_probe = $false
    }
    [IO.File]::WriteAllText($resultJson,(($result | ConvertTo-Json -Depth 8) + [Environment]::NewLine),(New-Object Text.UTF8Encoding($false)))
    $head = Push-Evidence "research(v0.10.5): static Raven save identity unavailable $stamp"
    throw "Static join is unavailable. Launch GoW in VikingFuneral/Veithurgard and rerun. Evidence pushed in $head"
}

$readerText = Get-Content -LiteralPath $liveReader -Raw
foreach ($forbidden in @('DebugActiveProcess','WriteProcessMemory','VirtualProtectEx','0xCC','PROCESS_VM_WRITE')) {
    if ($readerText.Contains($forbidden)) {
        throw "Read-only identity reader contains forbidden process-mutation token: $forbidden"
    }
}

Write-Host ''
Write-Host '  GoW is running.'
Write-Host '  This stage uses OpenProcess + ReadProcessMemory only.'
Write-Host '  Do NOT create a save or interact with the serializer; just leave Veithurgard loaded.'
Write-Host ''

$liveExit = Invoke-PythonLogged -PythonPrefix $python -Script $liveReader -Arguments @('--output',$liveJson) -Log $liveLog

$result = [ordered]@{
    schema = 1
    captured_utc = (Get-Date).ToUniversalTime().ToString('o')
    static_result = $staticResult.result
    static_recipe_count = @($staticResult.common_recipe_matches).Count
    live_memory_attempted = $true
    live_memory_exit_code = $liveExit
    live_memory_complete = ($liveExit -eq 0 -and (Test-Path -LiteralPath $liveJson -PathType Leaf))
    save_or_progression_written_by_probe = $false
    process_memory_written_by_probe = $false
    debugger_attached = $false
}
if ($result.live_memory_complete) {
    $live = Get-Content -LiteralPath $liveJson -Raw | ConvertFrom-Json
    $result['resolved_records'] = @($live.records).Count
    $result['identity_method_rvas'] = @(
        $live.records | ForEach-Object { $_.object.identity_method_rva } | Sort-Object -Unique
    )
    $result['direct_vector_matches'] = @(
        $live.records | ForEach-Object {
            [ordered]@{
                catalogue_id = $_.catalogue_id
                object_hash_hex = $_.object_hash_hex
                match_count = @($_.identity_vector_memory_scan.matches).Count
            }
        }
    )
    $result['result'] = 'RAVEN_LIVE_MEMORY_IDENTITY_READ'
}
else {
    $result['result'] = 'RAVEN_LIVE_MEMORY_IDENTITY_READ_FAILED'
}

[IO.File]::WriteAllText($resultJson,(($result | ConvertTo-Json -Depth 12) + [Environment]::NewLine),(New-Object Text.UTF8Encoding($false)))
$message = if ($result.live_memory_complete) { "research(v0.10.5): read Raven live GameObject identity safely $stamp" } else { "research(v0.10.5): archive failed read-only Raven live-memory identity $stamp" }
$head = Push-Evidence $message

if (-not $result.live_memory_complete) {
    throw "Read-only live GameObject identity inspection failed; evidence pushed in $head"
}

Write-Host "RAVEN_SAVE_IDENTITY_LIVE_MEMORY_PUSHED $head"
