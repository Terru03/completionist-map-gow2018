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
    throw 'Close God of War before collecting and rolling back the native Raven runtime probe.'
}

$log = Join-Path $GameRoot 'mods\loader_log.txt'
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
    throw "Loader log missing: $log"
}

$lines = @(
    Select-String -LiteralPath $log -SimpleMatch '[CompletionistMap v0.10.3]' |
        ForEach-Object { $_.Line.TrimEnd() }
)
if ($lines.Count -eq 0) {
    throw 'No v0.10.3 runtime lines found. Leave the runtime probe installed and verify the game/map was opened.'
}

$candidateInfo = @($lines | Where-Object { $_ -match 'NATIVE_MARKER_INFO source=candidate ' })
$candidateMissing = @($lines | Where-Object { $_ -match 'NATIVE_MARKER_LOOKUP source=candidate registered=false' })
$candidatePosition = @($lines | Where-Object { $_ -match 'NATIVE_MARKER_POSITION source=candidate ' })
$unsafeShow = @($lines | Where-Object { $_ -match 'show_attempted=true' })

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v103-native-dcb-runtime.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out, $lines, $utf8)
Write-Host "Saved native DCB runtime report: $out"
Write-Host "Matched lines: $($lines.Count)"

& (Join-Path $PSScriptRoot 'native-raven-runtime-probe.ps1') -Mode Remove -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Native Raven runtime rollback failed.' }

$result = if ($unsafeShow.Count -gt 0) {
    'UNEXPECTED_COMPASS_CALL'
} elseif ($candidateInfo.Count -gt 0 -and $candidatePosition.Count -gt 0 -and $candidateMissing.Count -eq 0) {
    'NATIVE_RAVEN_REGISTERED'
} else {
    'NATIVE_RAVEN_NOT_REGISTERED'
}

Write-Host "Runtime result: $result"
if ($candidatePosition.Count -gt 0) {
    $candidatePosition | ForEach-Object { Write-Host $_ }
}
Write-Host 'Compass.ShowMarker expected/called: False'

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
        git commit -m 'Archive native Raven DCB runtime lookup' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Pushed runtime report to $Remote/$branch"
    }
} finally {
    Pop-Location
}

if ($result -eq 'UNEXPECTED_COMPASS_CALL') {
    throw 'Unexpected ShowMarker call appeared in the runtime log.'
}
if ($result -ne 'NATIVE_RAVEN_REGISTERED') {
    throw 'Runtime DCBs loaded, but the Raven did not register as expected. Inspect the pushed report before further testing.'
}

Write-Host 'Native Raven registration proof PASSED. Do not test Add to Compass yet.'
