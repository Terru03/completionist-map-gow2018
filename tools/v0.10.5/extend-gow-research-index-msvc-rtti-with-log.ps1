param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$exe = 'G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe'
$db = Join-Path $repo '.research-index\gow-caebcb027980.sqlite'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relative = "archive/field-logs/source-scans/gow-msvc-rtti-index-$stamp"
$outDir = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$json = Join-Path $outDir 'gow-msvc-rtti-index.json'
$text = Join-Path $outDir 'gow-msvc-rtti-index.txt'
$pythonOutput = Join-Path $outDir 'python-output.txt'
$published = $false
$transcript = $false

function Publish([string]$Result) {
    if ($script:published) { return }
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        "local_index=$db"
        'phase=msvc_rtti_vtable_index_extension'
        'exe_rescanned=targeted-rtti-metadata-read-only'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

    & git add -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relative
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Archive GoW MSVC RTTI index $stamp" -- $relative | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin "HEAD:$expectedBranch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff failed.'
    }
    $script:published = $true
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true

    Write-Host '=== Completionist Map MSVC RTTI/vtable index extension ==='
    Write-Host 'Builds reusable RTTI/vtable tables from the existing static pointer index.'
    Write-Host 'No game launch and no save I/O.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing staged changes: $($staged -join ', ')" }

    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "GoW.exe missing: $exe" }
    if (-not (Test-Path -LiteralPath $db -PathType Leaf)) { throw "Reusable index missing: $db" }
    $scriptPath = Join-Path $repo 'tools\v0.10.5\extend-gow-research-index-msvc-rtti.py'
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw 'RTTI index extension missing.' }

    $pythonCmd = Get-Command python.exe -ErrorAction Stop
    $pythonExe = $pythonCmd.Source
    Write-Host "PYTHON_EXE=$pythonExe"
    Write-Host "PYTHON_SCRIPT=$scriptPath"

    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $pythonExe -I $scriptPath --exe $exe --db $db --output-json $json --output-text $text 2>&1 | Tee-Object -FilePath $pythonOutput
        $pythonExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldEap
    }
    if ($pythonExit -ne 0) { throw "RTTI index extension exited $pythonExit. Full output: $pythonOutput" }

    Publish 'INDEX_EXTENSION_PASSED'
    Write-Host 'GOW_MSVC_RTTI_INDEX_EXTENSION_PASSED_AND_PUSHED' -ForegroundColor Green
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "INDEX_EXTENSION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish 'INDEX_EXTENSION_FAILED' } catch { Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    if ($transcript) { try { Stop-Transcript | Out-Null } catch {} }
}
