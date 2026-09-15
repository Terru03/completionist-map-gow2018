$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script = Join-Path $PSScriptRoot 'trace-gow-decoder-userdata-branch.py'
$exe = 'G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$archive = Join-Path $repo "archive\field-logs\source-scans\gow-decoder-userdata-branch-$timestamp"
New-Item -ItemType Directory -Force -Path $archive | Out-Null
$consoleLog = Join-Path $archive 'console-log.txt'
$pythonOut = Join-Path $archive 'python-output.txt'
$jsonOut = Join-Path $archive 'gow-decoder-userdata-branch.json'
$textOut = Join-Path $archive 'gow-decoder-userdata-branch.txt'
$resultOut = Join-Path $archive 'result.txt'
$errorOut = Join-Path $archive 'error.txt'

Start-Transcript -Path $consoleLog -Force | Out-Null
try {
    Write-Host '=== Completionist Map decoder userdata/type branch trace ==='
    Write-Host 'Targeted read-only codec-band disassembly; no game launch/save I/O.'

    if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Missing Python script: $script" }
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Missing GoW.exe: $exe" }

    $python = (Get-Command python.exe -ErrorAction Stop).Source
    Write-Host "PYTHON_EXE=$python"
    Write-Host "PYTHON_SCRIPT=$script"

    & $python -I -m py_compile $script
    if ($LASTEXITCODE -ne 0) { throw "py_compile failed with exit code $LASTEXITCODE" }

    & $python -I $script --exe $exe --output-json $jsonOut --output-text $textOut 2>&1 | Tee-Object -FilePath $pythonOut
    if ($LASTEXITCODE -ne 0) { throw "Decoder userdata tracer exited $LASTEXITCODE. Full output: $pythonOut" }

    @(
        'result=ANALYSIS_PASSED'
        "timestamp=$((Get-Date).ToString('o'))"
        'branch=codex/all-collectibles-production-research'
        'analysis=gow_decoder_userdata_branch'
        'exe_rescanned=targeted-codec-band-only'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
    ) | Set-Content -LiteralPath $resultOut -Encoding UTF8

    Stop-Transcript | Out-Null
    Push-Location $repo
    try {
        git add -- $archive
        git commit -m "Archive GoW decoder userdata branch $timestamp"
        if ($LASTEXITCODE -ne 0) { throw "git commit failed with exit code $LASTEXITCODE" }
        git push origin codex/all-collectibles-production-research
        if ($LASTEXITCODE -ne 0) { throw "git push failed with exit code $LASTEXITCODE" }
    }
    finally { Pop-Location }

    Write-Host 'GOW_DECODER_USERDATA_BRANCH_PASSED_AND_PUSHED'
}
catch {
    $_ | Out-String | Set-Content -LiteralPath $errorOut -Encoding UTF8
    @(
        'result=ANALYSIS_FAILED'
        "timestamp=$((Get-Date).ToString('o'))"
        'branch=codex/all-collectibles-production-research'
        'analysis=gow_decoder_userdata_branch'
        'exe_rescanned=targeted-codec-band-only'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
    ) | Set-Content -LiteralPath $resultOut -Encoding UTF8
    try { Stop-Transcript | Out-Null } catch {}
    Push-Location $repo
    try {
        git add -- $archive
        git commit -m "Archive failed GoW decoder userdata branch $timestamp"
        if ($LASTEXITCODE -eq 0) { git push origin codex/all-collectibles-production-research | Out-Host }
    }
    finally { Pop-Location }
    throw
}
