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
    throw 'Close God of War completely before collecting the successful native Raven data A/B.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
$ab = Join-Path $PSScriptRoot 'native-raven-data-ab.py'
if (-not (Test-Path -LiteralPath $ab -PathType Leaf)) { throw "Missing A/B tool: $ab" }

$stateRoot = Join-Path $repo 'build\v0.10.4\native-raven-no-render\ab-transactions'
if (-not (Test-Path -LiteralPath $stateRoot -PathType Container)) {
    throw "A/B transaction state directory missing: $stateRoot"
}

$installed = @()
Get-ChildItem -LiteralPath $stateRoot -Recurse -Filter manifest.json -File | ForEach-Object {
    try {
        $value = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
        if ([string]$value.kind -eq 'v104-native-raven-coordinate-graph-ab-v1' -and [string]$value.state -eq 'installed') {
            $installed += $_.FullName
        }
    } catch {
        # Ignore unrelated/malformed historical files; exact installed transaction count is checked below.
    }
}
if ($installed.Count -ne 1) {
    throw "Expected exactly one installed native Raven A/B transaction, found $($installed.Count)."
}
$manifest = $installed[0]

$before = @(Get-ChildItem -LiteralPath (Join-Path $repo 'archive\field-logs') -Filter 'completionist-v104-native-raven-data-ab-*.json' -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)

& $python.Source $ab --mode collect --game-root $GameRoot --manifest $manifest --hud visible --world unknown
if ($LASTEXITCODE -ne 0) { throw 'Native Raven A/B evidence collection failed.' }

$after = @(Get-ChildItem -LiteralPath (Join-Path $repo 'archive\field-logs') -Filter 'completionist-v104-native-raven-data-ab-*.json' -File | Select-Object -ExpandProperty FullName)
$newFiles = @($after | Where-Object { $_ -notin $before })
if ($newFiles.Count -ne 1) {
    throw "Expected exactly one new A/B evidence report, found $($newFiles.Count)."
}
$report = $newFiles[0]
$rel = [IO.Path]::GetRelativePath($repo, $report).Replace('\','/')

Push-Location $repo
try {
    git add -- $rel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $rel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git commit -m 'Archive successful native Raven data A/B' -- $rel
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    git push $Remote $branch
    if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host 'NATIVE_RAVEN_DATA_AB_SUCCESS_ARCHIVED'
Write-Host ("  manifest: {0}" -f $manifest)
Write-Host ("  report:   {0}" -f $report)
Write-Host '  user-observed HUD/native navigation: visible/working'
Write-Host '  world marker observation recorded as: unknown'
Write-Host '  A/B remains installed for the next class-only test'
