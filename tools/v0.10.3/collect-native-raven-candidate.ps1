param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin',
    [switch]$RemoveAfter
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.3-native-raven') {
    throw "Expected feat/v0.10.3-native-raven, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War completely before collecting the native Raven candidate log.'
}

$log = Join-Path $GameRoot 'mods\loader_log.txt'
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { throw "Loader log missing: $log" }
$lines = @(
    Select-String -LiteralPath $log -SimpleMatch '[CompletionistMap v0.10.3-native]' |
        ForEach-Object { $_.Line.TrimEnd() }
)
if ($lines.Count -eq 0) {
    throw 'No v0.10.3-native lines found. The existing field report was left untouched.'
}

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v103-native-raven-candidate.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out, $lines, $utf8)

$show = @($lines | Where-Object { $_ -match 'NATIVE_RAVEN_SHOW stage=lua_return ok=true' }).Count
$queued = @($lines | Where-Object { $_ -match 'NATIVE_RAVEN_RESULT request_queued=true active=true' }).Count
$verified = @($lines | Where-Object { $_ -match 'NATIVE_RAVEN_VERIFY active=true' }).Count
$legacyDisabled = @($lines | Where-Object { $_ -match 'LEGACY_R3L3_DISABLED' }).Count
$lifecycleClear = @($lines | Where-Object { $_ -match 'NATIVE_RAVEN_LIFECYCLE .*collected=true.*hideOK=true' }).Count

Write-Host "Saved native Raven candidate report: $out"
Write-Host "Matched lines: $($lines.Count)"
Write-Host "Native ShowMarker Lua returns: $show"
Write-Host "Native requests queued: $queued"
Write-Host "Native manager verification logs: $verified"
Write-Host "Legacy R3/L3 suppressions: $legacyDisabled"
Write-Host "Lifecycle auto-clears: $lifecycleClear"

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Candidate report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive v0.10.3 native Raven candidate field log' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Pushed candidate report to $Remote/$branch"
    }
} finally {
    Pop-Location
}

if ($RemoveAfter) {
    & (Join-Path $PSScriptRoot 'install-native-raven-candidate.ps1') -Mode Remove -GameRoot $GameRoot
}
