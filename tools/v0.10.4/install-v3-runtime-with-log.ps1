param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Repo = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Repo)) {
    throw 'Run this from inside the completionist-map-gow2018 repository.'
}
Set-Location $Repo

$Branch = 'codex/v104-raven-uid-compass-lifecycle-v3'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogRel = "archive/field-logs/runtime-captures/v3-install-$Stamp"
$LogDir = Join-Path $Repo $LogRel
$ConsoleLog = Join-Path $LogDir 'console-log.txt'
$Summary = Join-Path $LogDir 'result.txt'
$LoaderLog = Join-Path $GameRoot 'mods\loader_log.txt'

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Succeeded = $false
$FailureText = ''

function Write-Log([string]$Text = '') {
    $Text | Tee-Object -FilePath $ConsoleLog -Append | Out-Host
}

function Invoke-Captured([string]$Label, [scriptblock]$Command) {
    Write-Log ""
    Write-Log "=== $Label ==="

    # Windows PowerShell 5.1 can promote native stderr text to a terminating
    # NativeCommandError when the caller uses ErrorActionPreference=Stop. Git
    # legitimately writes warnings to stderr, so capture native output with
    # Continue and judge success solely by the process exit code.
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $lines = & $Command 2>&1 | ForEach-Object { $_.ToString() }
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }

    foreach ($line in $lines) { Write-Log $line }
    if ($code -ne 0) { throw "$Label failed (exit $code)." }
    return ,$lines
}

try {
    Write-Log 'COMPLETIONIST RAVEN UID LIFECYCLE V3 RUNTIME INSTALL'
    Write-Log "time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Log "repo: $Repo"
    Write-Log "game: $GameRoot"

    $current = (& git branch --show-current).Trim()
    if ($current -ne $Branch) { throw "Expected branch '$Branch', got '$current'." }

    & git diff --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Tracked working-tree changes exist.' }
    & git diff --cached --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Staged changes exist.' }

    Invoke-Captured 'SYNC V3' { & git pull --ff-only }
    Invoke-Captured 'V3 HEAD' { & git log -5 --oneline --decorate }

    if (Test-Path -LiteralPath $LoaderLog -PathType Leaf) {
        $item = Get-Item -LiteralPath $LoaderLog
        Write-Log "pretest_loader_log_bytes=$($item.Length)"
        Write-Log "pretest_loader_log_sha256=$((Get-FileHash -LiteralPath $LoaderLog -Algorithm SHA256).Hash.ToLowerInvariant())"
    }

    $statusBefore = Invoke-Captured 'V3 STATUS BEFORE INSTALL' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }

    $alreadyInstalled = @($statusBefore | Where-Object { $_ -match '^\s*status:\s*installed\s*$' }).Count -gt 0
    $noActive = @($statusBefore | Where-Object { $_ -match '^\s*active transaction:\s*none\s*$' }).Count -gt 0

    if ($alreadyInstalled) {
        Write-Log ''
        Write-Log 'V3 is already installed; skipping duplicate install.'
    }
    elseif ($noActive) {
        Invoke-Captured 'V3 INSTALL' {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3-runtime.ps1' -Mode Install -GameRoot $GameRoot -ConfirmRuntimeTest
        }
    }
    else {
        throw 'V3 has an active transaction in an unexpected non-installed state. Review before retrying.'
    }

    $statusAfter = Invoke-Captured 'V3 STATUS AFTER INSTALL' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\v0.10.4\raven-uid-compass-lifecycle-v3-runtime.ps1' -Mode Status -GameRoot $GameRoot
    }

    if (@($statusAfter | Where-Object { $_ -match '^\s*status:\s*installed\s*$' }).Count -eq 0) {
        throw 'V3 status after install does not report installed.'
    }

    $Succeeded = $true
    Write-Log ''
    Write-Log 'RESULT: PASS'
}
catch {
    $FailureText = ($_ | Out-String).Trim()
    Write-Log ''
    Write-Log 'RESULT: FAIL'
    Write-Log $FailureText
}
finally {
    @(
        "result=$(if ($Succeeded) { 'PASS' } else { 'FAIL' })",
        "time_local=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "game_root=$GameRoot",
        "failure=$($FailureText -replace "`r?`n", ' | ')"
    ) | Set-Content -LiteralPath $Summary -Encoding UTF8

    try {
        Set-Location $Repo
        $current = (& git branch --show-current).Trim()
        if ($current -ne $Branch) { throw "Cannot publish install log from unexpected branch '$current'." }
        & git add -- $LogRel
        if ($LASTEXITCODE -ne 0) { throw 'Could not stage install log.' }
        & git diff --cached --quiet
        if ($LASTEXITCODE -ne 0) {
            $message = if ($Succeeded) { 'Archive Raven lifecycle v3 runtime install pass' } else { 'Archive Raven lifecycle v3 runtime install failure' }
            & git commit -m $message | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not commit install log.' }
            & git push origin HEAD | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Could not push install log.' }
        }
    }
    catch {
        Write-Warning "Install log publication failed: $($_.Exception.Message)"
        Write-Warning "Local log remains at: $ConsoleLog"
    }
}

if (-not $Succeeded) {
    throw "V3 runtime install failed. Full log was archived under $LogRel when publication succeeded."
}

Write-Host "Done. V3 installed for human runtime testing. Log pushed under $LogRel."
