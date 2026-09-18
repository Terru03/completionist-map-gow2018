[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$branch='codex/all-collectibles-production-research'
$repo=(& git rev-parse --show-toplevel 2>$null).Trim()
if(-not $repo){ throw 'Not inside repository' }
Set-Location $repo
if((& git branch --show-current).Trim()-ne $branch){ throw 'Wrong branch' }

$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$rel="archive/field-logs/runtime-captures/luaclient-pickle-buffers-$stamp"
$out=Join-Path $repo $rel
New-Item -ItemType Directory -Force -Path $out | Out-Null
$log=Join-Path $out 'console-log.txt'
$errorFile=Join-Path $out 'error.txt'
$exitCode=0
$transcriptStarted=$false

function Publish-Evidence {
    param([string]$Message)
    try {
        & git add -f -- $rel
        if($LASTEXITCODE-ne 0){ throw 'git add failed' }
        & git diff --cached --quiet -- $rel
        if($LASTEXITCODE -eq 1){
            & git commit -m $Message -- $rel | Out-Host
            if($LASTEXITCODE-ne 0){ throw 'git commit failed' }
            & git push origin $branch | Out-Host
            if($LASTEXITCODE-ne 0){ throw 'git push failed' }
        } elseif($LASTEXITCODE-ne 0){
            throw 'git diff failed'
        }
    } catch {
        Write-Host "EVIDENCE_PUBLISH_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
}

try {
    Start-Transcript -LiteralPath $log -Force | Out-Null
    $transcriptStarted=$true

    $proc=@(
        Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }
    )
    if($proc.Count -eq 0){ throw 'God of War is not running (expected GoW.exe or GodOfWar.exe)' }
    if($proc.Count -gt 1){ throw "Multiple God of War processes found: $($proc.Id -join ',')" }

    $ids=Join-Path $repo 'catalogue\odins-ravens-save-identities.json'
    if(-not(Test-Path -LiteralPath $ids -PathType Leaf)){ throw "Missing identity catalogue: $ids" }

    $script=Join-Path $repo 'tools\v0.10.5\capture-luaclient-pickle-buffers.py'
    if(-not(Test-Path -LiteralPath $script -PathType Leaf)){ throw "Missing capture script: $script" }

    & python $script --identities $ids --output-dir $out 2>&1 | ForEach-Object { "$_"; Write-Host "$_" }
    $exitCode=$LASTEXITCODE
    if($exitCode-ne 0){ throw "LuaClient pickle-buffer capture exited $exitCode" }

    Write-Host "LUACLIENT_PICKLE_BUFFERS_CAPTURE_OK" -ForegroundColor Green
}
catch {
    $exitCode=1
    $_.Exception.ToString() | Set-Content -LiteralPath $errorFile -Encoding UTF8
    Write-Host "LUACLIENT_PICKLE_BUFFERS_CAPTURE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    if($transcriptStarted){
        try { Stop-Transcript | Out-Null } catch {}
    }
    $msg = if($exitCode -eq 0) {
        "research(v0.10.5): capture live LuaClient pickle buffers $stamp"
    } else {
        "research(v0.10.5): archive failed live LuaClient pickle buffers $stamp"
    }
    Publish-Evidence -Message $msg
}

if($exitCode-ne 0){ exit $exitCode }
Write-Host "LUACLIENT_PICKLE_BUFFERS_PUSHED $((& git rev-parse HEAD).Trim())" -ForegroundColor Green
