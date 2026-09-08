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
    throw 'Close God of War completely before collecting/rolling back the Raven HUD-art proof.'
}

$log = Join-Path $GameRoot 'mods\loader_log.txt'
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { throw "Loader log missing: $log" }

$stateDir = Join-Path $repo 'build\v0.10.4-packed-raven-hud-art-runtime'
$manifestPath = Join-Path $stateDir 'active.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw 'Raven HUD-art runtime manifest is missing. Refusing to infer or perform an unrelated rollback.'
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
    'PACKED_COMPLETIONIST_RAVEN_HUD_ART_CLASS_MANAGER_VERIFIED'
} elseif ($invalidLines.Count -gt 0 -or $showReturnFail.Count -gt 0) {
    'PACKED_COMPLETIONIST_RAVEN_HUD_ART_CLASS_REJECTED'
} elseif ($queued -and $showReturnOK.Count -gt 0) {
    'PACKED_COMPLETIONIST_RAVEN_HUD_ART_SHOW_ACCEPTED_NOT_MANAGER_VERIFIED'
} elseif ($showBefore.Count -gt 0) {
    'PACKED_COMPLETIONIST_RAVEN_HUD_ART_SHOW_ATTEMPT_INCOMPLETE'
} else {
    'NO_PACKED_COMPLETIONIST_RAVEN_HUD_ART_SHOW_REQUEST'
}

# Roll back first. The HUD installer delegates to the proven packed-class rollback,
# which restores all DCBs/mapmenu from its install-time byte-exact backups.
& (Join-Path $PSScriptRoot 'install-packed-raven-hud-art-proof.ps1') -Mode Remove -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Raven HUD-art rollback failed.' }

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v104-packed-raven-hud-art-runtime.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
$utf8 = New-Object Text.UTF8Encoding($false)
$reportLines = New-Object System.Collections.Generic.List[string]
$reportLines.Add('Completionist Map v0.10.4 HUD-only Raven compass artwork runtime proof')
$reportLines.Add(('Capture UTC: {0}' -f [DateTime]::UtcNow.ToString('o')))
$reportLines.Add(('Result: {0}' -f $result))
$reportLines.Add(('Candidate: {0}' -f [string]$manifest.candidate))
$reportLines.Add(('Candidate ID: {0}' -f [string]$manifest.candidate_hash))
$reportLines.Add(('Compass class: {0}' -f [string]$manifest.compass_class))
$reportLines.Add(('Compass class UID: {0}' -f [string]$manifest.compass_class_uid))
$reportLines.Add(('Compass class root: {0}' -f [string]$manifest.compass_class_root))
$reportLines.Add(('Base registration candidate SHA256: {0}' -f [string]$manifest.base_registration_candidate_sha256))
$reportLines.Add(('HUD candidate wad_r_perm SHA256: {0}' -f [string]$manifest.hud_candidate_sha256))
$reportLines.Add(('HUD IconName: {0}' -f [string]$manifest.hud_IconName))
$reportLines.Add(('HUD resource: {0}' -f [string]$manifest.hud_resource))
$reportLines.Add(('InWorld_tMPIcon_Name: {0}' -f [string]$manifest.InWorld_tMPIcon_Name))
$reportLines.Add(('Expected HUD visual: {0}' -f [string]$manifest.expected_hud_visual))
$reportLines.Add(('Expected in-world visual: {0}' -f [string]$manifest.expected_inworld_visual))
$reportLines.Add(('Expected map visual: {0}' -f [string]$manifest.expected_map_visual))
$reportLines.Add(('Class log lines: {0}' -f $lines.Count))
$reportLines.Add(('Invalid-type lines: {0}' -f $invalidLines.Count))
$reportLines.Add(('Show-before lines: {0}' -f $showBefore.Count))
$reportLines.Add(('Show-return-ok lines: {0}' -f $showReturnOK.Count))
$reportLines.Add(('Show-return-fail lines: {0}' -f $showReturnFail.Count))
$reportLines.Add(('Manager-verified: {0}' -f $verified))
$reportLines.Add('Visual result requires user observation; loader log cannot prove rendered glyph artwork.')
$reportLines.Add('Rollback completed before archival: true')
$reportLines.Add('Solved Raven map WAD/DCB/texpack modified by proof: false')
$reportLines.Add('Real DockPoint resources modified by proof: false')
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

Write-Host "Saved Raven HUD-art runtime report: $out"
Write-Host "Runtime result: $result"
Write-Host "Class lines: $($lines.Count); invalid-type lines: $($invalidLines.Count); verified: $verified"
Write-Host 'Baseline was rolled back before archival; solved Raven map resources were never modified.'

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'HUD-art runtime report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive Raven compass HUD artwork proof' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Pushed HUD-art runtime report to $Remote/$branch"
    }
} finally {
    Pop-Location
}

Write-Host ''
if ($verified) {
    Write-Host 'PASS: CompletionistRaven remained accepted/manager-verified with the HUD IconName override.'
    Write-Host 'Visual gate still depends on what you saw: compass should be Raven; floating in-world marker should still be DockPoint.'
} elseif ($result -eq 'PACKED_COMPLETIONIST_RAVEN_HUD_ART_CLASS_REJECTED') {
    Write-Host 'FAIL: class registration regressed under the HUD-only candidate. Do not proceed to in-world artwork.'
} else {
    Write-Host 'INCONCLUSIVE: no complete HUD-only runtime request was captured.'
}
