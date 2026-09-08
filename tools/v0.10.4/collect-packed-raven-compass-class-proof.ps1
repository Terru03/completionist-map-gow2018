param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War completely before collecting/rolling back the packed Raven class proof.'
}

$log = Join-Path $GameRoot 'mods\loader_log.txt'
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
    throw "Loader log missing: $log"
}

$stateDir = Join-Path $repo 'build\v0.10.4-packed-raven-runtime'
$manifestPath = Join-Path $stateDir 'active.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw 'Packed Raven runtime manifest is missing. Refusing to infer or perform an unrelated rollback.'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

$lines = @(
    Select-String -LiteralPath $log -SimpleMatch '[CompletionistMap v0.10.4-class]' |
        ForEach-Object { $_.Line.TrimEnd() }
)
$invalidLines = @(
    Select-String -LiteralPath $log -SimpleMatch "invalid type 'CompletionistRaven'" |
        ForEach-Object { $_.Line.TrimEnd() }
)
$showBefore = @($lines | Where-Object { $_ -match ' SHOW stage=before ' })
$showReturnOK = @($lines | Where-Object { $_ -match ' SHOW stage=lua_return ok=true' })
$showReturnFail = @($lines | Where-Object { $_ -match ' SHOW stage=lua_return ok=false' })
$queued = @($lines | Where-Object { $_ -match 'RESULT request_queued=true active=true class=CompletionistRaven' }).Count -gt 0
$verifyLines = @($lines | Where-Object { $_ -match ' VERIFY ' })
$verified = @($verifyLines | Where-Object { $_ -match 'active=true' -and $_ -match 'customClassManager=true' }).Count -gt 0

$result = if ($verified) {
    'PACKED_COMPLETIONIST_RAVEN_CLASS_ACCEPTED_AND_MANAGER_VERIFIED'
} elseif ($invalidLines.Count -gt 0 -or $showReturnFail.Count -gt 0) {
    'PACKED_COMPLETIONIST_RAVEN_CLASS_REJECTED'
} elseif ($queued -and $showReturnOK.Count -gt 0) {
    'PACKED_COMPLETIONIST_RAVEN_CLASS_SHOW_ACCEPTED_NOT_MANAGER_VERIFIED'
} elseif ($showBefore.Count -gt 0) {
    'PACKED_COMPLETIONIST_RAVEN_CLASS_SHOW_ATTEMPT_INCOMPLETE'
} else {
    'NO_PACKED_COMPLETIONIST_RAVEN_SHOW_REQUEST'
}

# Roll back before writing/committing the runtime report. This restores all four
# DCBs and mapmenu.lua byte-for-byte from the install-time backups.
& (Join-Path $PSScriptRoot 'install-packed-raven-compass-class-proof.ps1') -Mode Remove -GameRoot $GameRoot

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v104-packed-raven-class-runtime.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
$utf8 = New-Object Text.UTF8Encoding($false)
$reportLines = New-Object System.Collections.Generic.List[string]
$reportLines.Add('Completionist Map v0.10.4 packed Raven CompassIconClass runtime proof')
$reportLines.Add(('Capture UTC: {0}' -f [DateTime]::UtcNow.ToString('o')))
$reportLines.Add(('Result: {0}' -f $result))
$reportLines.Add(('Candidate: {0}' -f [string]$manifest.candidate))
$reportLines.Add(('Candidate ID: {0}' -f [string]$manifest.candidate_hash))
$reportLines.Add(('Compass class: {0}' -f [string]$manifest.compass_class))
$reportLines.Add(('Compass class UID: {0}' -f [string]$manifest.compass_class_hash))
$reportLines.Add(('Compass class root: {0}' -f [string]$manifest.compass_class_root))
$reportLines.Add(('Candidate wad_r_perm SHA256: {0}' -f [string]$manifest.candidate_wad_sha256))
$reportLines.Add(('Class log lines: {0}' -f $lines.Count))
$reportLines.Add(('Invalid-type lines: {0}' -f $invalidLines.Count))
$reportLines.Add(('Show-before lines: {0}' -f $showBefore.Count))
$reportLines.Add(('Show-return-ok lines: {0}' -f $showReturnOK.Count))
$reportLines.Add(('Show-return-fail lines: {0}' -f $showReturnFail.Count))
$reportLines.Add(('Manager-verified: {0}' -f $verified))
$reportLines.Add('Rollback completed before archival: true')
$reportLines.Add('Save/progression/marker-state writes by installer: false')
$reportLines.Add('')
$reportLines.Add('=== CompletionistRaven class log ===')
foreach ($line in $lines) { $reportLines.Add($line) }
if ($invalidLines.Count -gt 0) {
    $reportLines.Add('')
    $reportLines.Add('=== Native invalid-type lines ===')
    foreach ($line in $invalidLines) { $reportLines.Add($line) }
}
[IO.File]::WriteAllLines($out, $reportLines, $utf8)

Write-Host "Saved packed Raven class runtime report: $out"
Write-Host "Runtime result: $result"
Write-Host "Class lines: $($lines.Count); invalid-type lines: $($invalidLines.Count); verified: $verified"
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
        git commit -m 'Archive packed Raven compass class runtime proof' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Pushed runtime report to $Remote/$branch"
    }
} finally {
    Pop-Location
}

Write-Host ''
if ($verified) {
    Write-Host 'PASS: CompletionistRaven was accepted and the native compass manager returned the Raven through that class.'
} elseif ($result -eq 'PACKED_COMPLETIONIST_RAVEN_CLASS_SHOW_ACCEPTED_NOT_MANAGER_VERIFIED') {
    Write-Host 'PARTIAL PASS: ShowMarker accepted CompletionistRaven, but manager verification did not complete.'
} elseif ($result -eq 'PACKED_COMPLETIONIST_RAVEN_CLASS_REJECTED') {
    Write-Host 'FAIL: the packed class was still rejected. Do not proceed to Raven-specific artwork yet.'
} else {
    Write-Host 'INCONCLUSIVE: no complete packed-class runtime request was captured.'
}
