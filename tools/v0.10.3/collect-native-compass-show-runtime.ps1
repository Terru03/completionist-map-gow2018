param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'research/v0.10.3-native-compass') {
    throw "Expected research/v0.10.3-native-compass, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War completely before collecting/rolling back the native compass show proof.'
}

$log = Join-Path $GameRoot 'mods\loader_log.txt'
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
    throw "Loader log missing: $log"
}

$lines = @(
    Select-String -LiteralPath $log -SimpleMatch '[CompletionistMap v0.10.3]' |
        ForEach-Object { $_.Line.TrimEnd() }
)

$showLines = @($lines | Where-Object { $_ -match 'NATIVE_COMPASS_SHOW ' })
$verifyLines = @($lines | Where-Object { $_ -match 'NATIVE_COMPASS_VERIFY ' })
$verified = @($verifyLines | Where-Object { $_ -match 'candidateFound=true' }).Count -gt 0
$queued = @($lines | Where-Object { $_ -match 'NATIVE_COMPASS_RESULT request_queued=true active=true' }).Count -gt 0
$luaReturned = @($showLines | Where-Object { $_ -match 'stage=lua_return ok=true' }).Count -gt 0

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v103-native-compass-show.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
$utf8 = New-Object Text.UTF8Encoding($false)

if ($lines.Count -gt 0) {
    [IO.File]::WriteAllLines($out, $lines, $utf8)
} else {
    [IO.File]::WriteAllLines($out, @('[CompletionistMap v0.10.3] NO_RUNTIME_LINES_FOUND'), $utf8)
}
Write-Host "Saved native compass runtime report: $out"
Write-Host "Matched v0.10.3 lines: $($lines.Count)"

# Always attempt full rollback before interpreting the result.
& (Join-Path $PSScriptRoot 'native-compass-show-probe.ps1') -Mode Remove -GameRoot $GameRoot

$result = if ($verified) {
    'NATIVE_COMPASS_MANAGER_ACCEPTED_RAVEN'
} elseif ($queued -and $luaReturned) {
    'REQUEST_QUEUED_BUT_NOT_VERIFIED'
} elseif ($showLines.Count -gt 0) {
    'SHOW_REQUEST_ATTEMPTED_INCOMPLETE'
} else {
    'NO_SHOW_REQUEST_RECORDED'
}

Write-Host "Runtime result: $result"
if ($verifyLines.Count -gt 0) {
    $verifyLines | ForEach-Object { Write-Host $_ }
}
Write-Host 'Stock DCBs/mapmenu rollback attempted before this result was reported.'

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Runtime report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive native Raven compass show proof' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Pushed runtime report to $Remote/$branch"
    }
} finally {
    Pop-Location
}

if ($result -eq 'NO_SHOW_REQUEST_RECORDED') {
    throw 'No native ShowMarker request was recorded. Do not infer a compass result.'
}

Write-Host ''
if ($verified) {
    Write-Host 'Native manager verification PASSED: FindMarkersByIconClass returned the authored Raven ID after the queued request.'
    Write-Host 'Visual distance/routing still requires the screenshot/gameplay observation.'
} else {
    Write-Host 'The native request did not reach the 30-frame manager verification in the log.'
    Write-Host 'Inspect the pushed report and any crash behaviour before another attempt.'
}
