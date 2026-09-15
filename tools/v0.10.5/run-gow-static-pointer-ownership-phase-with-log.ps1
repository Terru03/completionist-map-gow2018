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
$relative = "archive/field-logs/source-scans/gow-static-pointer-ownership-phase-$stamp"
$outDir = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$extJson = Join-Path $outDir 'gow-data-pointer-index.json'
$extText = Join-Path $outDir 'gow-data-pointer-index.txt'
$extOut = Join-Path $outDir 'data-pointer-python-output.txt'
$ownJson = Join-Path $outDir 'gow-static-pointer-ownership.json'
$ownText = Join-Path $outDir 'gow-static-pointer-ownership.txt'
$ownOut = Join-Path $outDir 'ownership-python-output.txt'
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
        'phase=data_ptr_extension_plus_static_pointer_ownership'
        'exe_rescanned=nonexec-pointer-sections-only'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

    & git add -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relative
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Archive GoW static pointer ownership phase $stamp" -- $relative | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin "HEAD:$expectedBranch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff failed.'
    }
    $script:published = $true
}

function Invoke-PythonLogged([string[]]$Args, [string]$OutputPath) {
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & python @Args 2>&1 | Tee-Object -FilePath $OutputPath
        $exit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldEap
    }
    if ($exit -ne 0) { throw "Python exited $exit. Full output: $OutputPath" }
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true

    Write-Host '=== Completionist Map combined static pointer ownership phase ==='
    Write-Host 'Step 1: extend SQLite with non-executable PE pointer tables.'
    Write-Host 'Step 2: correlate those tables with GameObject/persistence ownership.'
    Write-Host 'No game launch and no save I/O.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing staged changes: $($staged -join ', ')" }

    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "GoW.exe missing: $exe" }
    if (-not (Test-Path -LiteralPath $db -PathType Leaf)) { throw "Reusable index missing: $db" }

    $ext = Join-Path $repo 'tools\v0.10.5\extend-gow-research-index-data-pointers.py'
    $own = Join-Path $repo 'tools\v0.10.5\analyze-gow-static-pointer-ownership.py'
    if (-not (Test-Path -LiteralPath $ext -PathType Leaf)) { throw 'Pointer extension tool missing.' }
    if (-not (Test-Path -LiteralPath $own -PathType Leaf)) { throw 'Pointer ownership analyzer missing.' }

    Invoke-PythonLogged @($ext,'--exe',$exe,'--db',$db,'--output-json',$extJson,'--output-text',$extText) $extOut
    Invoke-PythonLogged @($own,'--db',$db,'--output-json',$ownJson,'--output-text',$ownText) $ownOut

    Publish 'PHASE_PASSED'
    Write-Host 'GOW_STATIC_POINTER_OWNERSHIP_PHASE_PASSED_AND_PUSHED' -ForegroundColor Green
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "PHASE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish 'PHASE_FAILED' } catch { Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    if ($transcript) { try { Stop-Transcript | Out-Null } catch {} }
}
