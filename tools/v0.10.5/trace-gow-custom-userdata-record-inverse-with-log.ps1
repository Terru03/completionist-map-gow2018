$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script = Join-Path $PSScriptRoot 'trace-gow-custom-userdata-record-inverse.py'
$exe = 'G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe'
$db = Join-Path $repo '.research-index\gow-caebcb027980.sqlite'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$archive = Join-Path $repo "archive\field-logs\source-scans\gow-custom-userdata-record-inverse-$timestamp"
New-Item -ItemType Directory -Force -Path $archive | Out-Null
$consoleLog = Join-Path $archive 'console-log.txt'
$pythonOut = Join-Path $archive 'python-output.txt'
$jsonOut = Join-Path $archive 'gow-custom-userdata-record-inverse.json'
$textOut = Join-Path $archive 'gow-custom-userdata-record-inverse.txt'
$resultOut = Join-Path $archive 'result.txt'
$errorOut = Join-Path $archive 'error.txt'

Start-Transcript -Path $consoleLog -Force | Out-Null
try {
    Write-Host '=== Completionist Map custom userdata record inverse trace ==='
    Write-Host 'Uses reusable SQLite call graph and targeted reachable-function disassembly.'
    Write-Host 'No game launch and no save I/O.'

    if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Missing Python script: $script" }
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Missing GoW.exe: $exe" }
    if (-not (Test-Path -LiteralPath $db -PathType Leaf)) { throw "Missing reusable research index: $db" }

    $python = (Get-Command python.exe -ErrorAction Stop).Source
    Write-Host "PYTHON_EXE=$python"
    Write-Host "PYTHON_SCRIPT=$script"
    Write-Host "INDEX=$db"

    & $python -I -m py_compile $script
    if ($LASTEXITCODE -ne 0) { throw "py_compile failed with exit code $LASTEXITCODE" }

    & $python -I $script --exe $exe --db $db --output-json $jsonOut --output-text $textOut 2>&1 | Tee-Object -FilePath $pythonOut
    if ($LASTEXITCODE -ne 0) { throw "Custom userdata inverse tracer exited $LASTEXITCODE. Full output: $pythonOut" }

    @(
        'result=ANALYSIS_PASSED'
        "timestamp=$((Get-Date).ToString('o'))"
        'branch=codex/all-collectibles-production-research'
        'analysis=gow_custom_userdata_record_inverse'
        'exe_rescanned=targeted-reachable-functions-only'
        'index_query=true'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
    ) | Set-Content -LiteralPath $resultOut -Encoding UTF8

    Stop-Transcript | Out-Null
    Push-Location $repo
    try {
        git add -- $archive
        git commit -m "Archive GoW custom userdata inverse $timestamp"
        if ($LASTEXITCODE -ne 0) { throw "git commit failed with exit code $LASTEXITCODE" }
        git push origin codex/all-collectibles-production-research
        if ($LASTEXITCODE -ne 0) { throw "git push failed with exit code $LASTEXITCODE" }
    }
    finally { Pop-Location }

    Write-Host 'GOW_CUSTOM_USERDATA_RECORD_INVERSE_PASSED_AND_PUSHED'
}
catch {
    $_ | Out-String | Set-Content -LiteralPath $errorOut -Encoding UTF8
    @(
        'result=ANALYSIS_FAILED'
        "timestamp=$((Get-Date).ToString('o'))"
        'branch=codex/all-collectibles-production-research'
        'analysis=gow_custom_userdata_record_inverse'
        'exe_rescanned=targeted-reachable-functions-only'
        'index_query=true'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
    ) | Set-Content -LiteralPath $resultOut -Encoding UTF8
    try { Stop-Transcript | Out-Null } catch {}
    Push-Location $repo
    try {
        git add -- $archive
        git commit -m "Archive failed GoW custom userdata inverse $timestamp"
        if ($LASTEXITCODE -eq 0) { git push origin codex/all-collectibles-production-research | Out-Host }
    }
    finally { Pop-Location }
    throw
}
