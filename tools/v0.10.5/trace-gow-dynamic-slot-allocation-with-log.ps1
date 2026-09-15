param(
    [string]$Exe = "G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe",
    [string]$Db = ".research-index\gow-caebcb027980.sqlite"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$tool = Join-Path $repo "tools\v0.10.5\trace-gow-dynamic-slot-allocation-fixed.py"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archive = Join-Path $repo "archive\field-logs\source-scans\gow-dynamic-slot-allocation-$stamp"
New-Item -ItemType Directory -Force -Path $archive | Out-Null
$console = Join-Path $archive "console-log.txt"
$result = Join-Path $archive "result.txt"
$json = Join-Path $archive "gow-dynamic-slot-allocation.json"
$txt = Join-Path $archive "gow-dynamic-slot-allocation.txt"
$pyout = Join-Path $archive "python-output.txt"

$failed = $false
$failureMessage = $null

Start-Transcript -Path $console | Out-Null
try {
    Write-Host "=== Completionist Map GoW dynamic slot allocation ==="
    Write-Host "Read-only no-hint allocator trace. No game launch or save access."

    python -m py_compile $tool
    if ($LASTEXITCODE -ne 0) { throw "py_compile failed (exit $LASTEXITCODE)" }

    python $tool --self-test
    if ($LASTEXITCODE -ne 0) { throw "self-test failed (exit $LASTEXITCODE)" }

    python $tool --exe $Exe --db $Db --output-json $json --output-text $txt 2>&1 | Tee-Object -FilePath $pyout
    $analysisExit = $LASTEXITCODE
    if ($analysisExit -ne 0) { throw "analysis failed (exit $analysisExit)" }

    $report = Get-Content $json -Raw | ConvertFrom-Json
    @(
        "result=ANALYSIS_PASSED"
        "timestamp=$((Get-Date).ToString('o'))"
        "branch=codex/all-collectibles-production-research"
        "analysis=gow_dynamic_slot_allocation"
        "analysis_mode=read-only"
        "status=$($report.status)"
        "gameobject_persistent_key_status=$($report.gameobject_persistent_key_status)"
        "production_oracle_status=$($report.production_oracle_status)"
        "frozen_save_probe=false"
        "game_launched=false"
        "active_save_opened=false"
        "active_save_modified=false"
        "save_or_progression_written=false"
        "exe_written=false"
    ) | Set-Content -Encoding UTF8 $result
}
catch {
    $failed = $true
    $failureMessage = $_.Exception.Message
    Write-Host "ANALYSIS_FAILED: $failureMessage"
    @(
        "result=ANALYSIS_FAILED"
        "timestamp=$((Get-Date).ToString('o'))"
        "branch=codex/all-collectibles-production-research"
        "analysis=gow_dynamic_slot_allocation"
        "analysis_mode=read-only"
        "failure=$failureMessage"
        "frozen_save_probe=false"
        "game_launched=false"
        "active_save_opened=false"
        "active_save_modified=false"
        "save_or_progression_written=false"
        "exe_written=false"
    ) | Set-Content -Encoding UTF8 $result
}
finally {
    Stop-Transcript | Out-Null
}

git add -- $archive
if (-not (git diff --cached --quiet)) {
    $kind = if ($failed) { "failure" } else { "result" }
    git commit -m "Archive GoW dynamic slot allocation $kind $stamp"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
    git push origin codex/all-collectibles-production-research
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }
}

if ($failed) {
    Write-Host "Failure archived and pushed: $failureMessage"
    exit 1
}
