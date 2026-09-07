param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (git -C $repo branch --show-current).Trim()
if ($branch -ne 'research/v0.10.3-native-compass') {
    throw "Expected research/v0.10.3-native-compass, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before collecting/rolling back the lookup probe.'
}

$log = Join-Path $GameRoot 'mods\loader_log.txt'
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
    throw "Loader log missing: $log"
}

$lines = @(
    Select-String -LiteralPath $log -SimpleMatch '[CompletionistMap v0.10.3]' |
        ForEach-Object { $_.Line }
)
if ($lines.Count -eq 0) {
    throw 'No v0.10.3 lookup-probe lines found. Do not remove the probe yet; verify the game/map was opened and inspect loader_log.txt.'
}

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$out = Join-Path $archiveDir 'completionist-v103-native-runtime.txt'
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out, $lines, $utf8)

Write-Host "Saved runtime lookup report: $out"
Write-Host "Matched lines: $($lines.Count)"

& (Join-Path $PSScriptRoot 'lookup-probe.ps1') -Mode Remove -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Lookup probe rollback failed.'
}

Push-Location $repo
try {
    git add -- 'archive/field-logs/completionist-v103-native-runtime.txt'
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }

    git diff --cached --check
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Runtime report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive native marker lookup baseline'
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push origin research/v0.10.3-native-compass
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host 'Pushed runtime lookup report to origin/research/v0.10.3-native-compass'
    }
} finally {
    Pop-Location
}

Write-Host 'Lookup probe removed and original map override restored.'
