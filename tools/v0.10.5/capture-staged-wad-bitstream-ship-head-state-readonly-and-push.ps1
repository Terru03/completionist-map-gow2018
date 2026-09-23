[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/collectible-ship-heads'
$RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$PythonProbe = Join-Path $PSScriptRoot 'capture-staged-wad-bitstream-ship-head-state-readonly.py'
Set-Location -LiteralPath $RepoRoot

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
$relative = "archive/field-logs/runtime-captures/staged-wad-bitstream-ship-head-$stamp-$suffix"
$out = Join-Path $RepoRoot $relative
New-Item -ItemType Directory -Path $out -Force | Out-Null
$consoleLog = Join-Path $out 'console-log.txt'
$published = $false
$transcriptStarted = $false
$captureCode = 1

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
        $script:transcriptStarted = $false
    }
}

function Publish-Evidence([string]$Result) {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$ExpectedBranch"
        "capture_scope=all_native_staged_wad_records"
        "current_streamed_zone_required=false"
        "process_memory_written=false"
        "hook_installed=false"
        "save_opened_by_probe=false"
        "save_written_by_probe=false"
        "progression_written_by_probe=false"
    ) | Set-Content -LiteralPath (Join-Path $out 'result.txt') -Encoding UTF8

    & git add -f -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'git add of Ship Head staged capture failed.' }
    & git diff --cached --quiet -- $relative
    if ($LASTEXITCODE -eq 0) { return }
    if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged Ship Head capture.' }

    $message = if ($Result -eq 'CAPTURE_PASSED') {
        "research(v0.10.5): capture global staged Ship Head state $stamp"
    } else {
        "research(v0.10.5): archive failed staged Ship Head state capture $stamp"
    }
    & git commit --only -m $message -- $relative | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git commit of Ship Head staged capture failed.' }

    & git fetch origin $ExpectedBranch | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git fetch before evidence push failed.' }
    & git rebase "origin/$ExpectedBranch" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git rebase before evidence push failed; capture commit remains local.' }
    & git push origin "HEAD:refs/heads/$ExpectedBranch" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git push failed; capture commit remains local.' }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== GLOBAL STAGED WAD SHIP HEAD STATE CAPTURE ==='
    Write-Host 'Scope: every WAD record in the native staged table, not only the currently streamed zone.'
    Write-Host 'Access: PROCESS_VM_READ | PROCESS_QUERY_INFORMATION only. No hook and no process-memory write.'

    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
        throw "Wrong branch: '$branch'. Expected '$ExpectedBranch'."
    }

    $foreignChanges = @(& git status --porcelain | Where-Object {
        $line = "$_"
        if ($line.Length -lt 4) { return $true }
        $path = $line.Substring(3).Replace('\\','/')
        -not $path.StartsWith(($relative + '/'), [System.StringComparison]::OrdinalIgnoreCase)
    })
    if ($foreignChanges.Count -gt 0) {
        throw "Working tree has unrelated changes: $($foreignChanges -join '; ')"
    }

    if (-not (Test-Path -LiteralPath $PythonProbe -PathType Leaf)) {
        throw "Probe missing: $PythonProbe"
    }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $python) { throw 'Python executable not found on PATH.' }

    $gow = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') })
    if ($gow.Count -ne 1) {
        throw 'Expected exactly one running God of War process with the target save loaded.'
    }

    Write-Host 'Keep the loaded game PAUSED while the two equal snapshots are taken.' -ForegroundColor Cyan
    & $python.Source $PythonProbe --output-dir $out 2>&1 | Tee-Object -FilePath (Join-Path $out 'python-output.txt')
    $captureCode = $LASTEXITCODE
    if ($captureCode -ne 0) { throw "Ship Head staged reader exited with code $captureCode" }
    if (-not (Test-Path -LiteralPath (Join-Path $out 'report.json') -PathType Leaf)) {
        throw 'Probe returned without report.json.'
    }

    Publish-Evidence 'CAPTURE_PASSED'
    $head = (& git rev-parse HEAD).Trim()
    Write-Host "GLOBAL_SHIP_HEAD_STATE_CAPTURE_PUSHED $head" -ForegroundColor Green
}
catch {
    $captureCode = if ($captureCode -eq 0) { 1 } else { $captureCode }
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $out 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SHIP_HEAD_STAGED_CAPTURE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try {
        Publish-Evidence 'CAPTURE_FAILED'
        Write-Host 'Failure evidence committed and pushed.' -ForegroundColor Yellow
    }
    catch {
        Write-Host "EVIDENCE_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 1
}
finally {
    Stop-LocalTranscript
}
