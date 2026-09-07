param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') {
    throw "Expected feat/v0.10.4-all-ravens, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War completely before collecting/rolling back the dedicated Raven class proof.'
}

$log = Join-Path $GameRoot 'mods\loader_log.txt'
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
    throw "Loader log missing: $log"
}

$lines = @(
    Select-String -LiteralPath $log -SimpleMatch '[CompletionistMap v0.10.4-class]' |
        ForEach-Object { $_.Line.TrimEnd() }
)
$showLines = @($lines | Where-Object { $_ -match ' SHOW ' })
$queued = @($lines | Where-Object { $_ -match 'RESULT request_queued=true active=true class=CompletionistRaven' }).Count -gt 0
$luaReturned = @($showLines | Where-Object { $_ -match 'stage=lua_return ok=true' }).Count -gt 0
$verifyLines = @($lines | Where-Object { $_ -match 'VERIFY ' })
$verified = @($verifyLines | Where-Object { $_ -match 'active=true' -and $_ -match 'customClassManager=true' }).Count -gt 0

# Always roll the core permanent DCB and the three Raven DCBs back before
# interpreting the result. This also restores mapmenu.lua byte-for-byte.
& (Join-Path $PSScriptRoot 'install-dedicated-raven-compass-class-proof.ps1') -Mode Remove -GameRoot $GameRoot

if ($lines.Count -eq 0) {
    Write-Host 'Matched v0.10.4-class lines: 0'
    Write-Host 'No new dedicated-class runtime lines were found.'
    Write-Host 'Existing archived proof evidence, if any, was not overwritten.'
    throw 'No CompletionistRaven runtime request was recorded. Rollback was still completed.'
}

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v104-dedicated-raven-class-runtime.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out, $lines, $utf8)
Write-Host "Saved dedicated Raven class runtime report: $out"
Write-Host "Matched v0.10.4-class lines: $($lines.Count)"

$result = if ($verified) {
    'DEDICATED_COMPLETIONIST_RAVEN_CLASS_ACCEPTED'
} elseif ($queued -and $luaReturned) {
    'DEDICATED_CLASS_REQUEST_QUEUED_BUT_NOT_VERIFIED'
} elseif ($showLines.Count -gt 0) {
    'DEDICATED_CLASS_SHOW_ATTEMPTED_INCOMPLETE'
} else {
    'NO_DEDICATED_CLASS_SHOW_REQUEST'
}
Write-Host "Runtime result: $result"
$verifyLines | ForEach-Object { Write-Host $_ }
Write-Host 'All four stock DCBs and mapmenu.lua were rolled back before archival.'

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
        git commit -m 'Archive dedicated Raven compass class runtime proof' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Pushed runtime report to $Remote/$branch"
    }
} finally {
    Pop-Location
}

if ($result -eq 'NO_DEDICATED_CLASS_SHOW_REQUEST') {
    throw 'No CompletionistRaven ShowMarker request was recorded. Do not infer a class result.'
}

Write-Host ''
if ($verified) {
    Write-Host 'PASS: the native compass manager returned the Raven through the independent CompletionistRaven class.'
    Write-Host 'Gameplay observation should also confirm the HUD marker/distance remained native.'
} elseif ($queued -and $luaReturned) {
    Write-Host 'The new class passed the Lua ShowMarker wrapper, but manager verification was not reached.'
    Write-Host 'Inspect the pushed report and any crash/visual behaviour before another test.'
} else {
    Write-Host 'The dedicated class request did not complete cleanly. Inspect the archived log before retrying.'
}
