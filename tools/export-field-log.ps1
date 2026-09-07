param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',

    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'

$repo = (& git rev-parse --show-toplevel).Trim()
if (-not $repo) {
    throw 'Run this script from inside the Completionist Map Git repository.'
}

$branch = (& git branch --show-current).Trim()
if (-not $branch) {
    throw 'Detached HEAD is not supported for automatic field-log pushes.'
}

$log = Join-Path $GameRoot 'mods\loader_log.txt'
if (-not (Test-Path $log)) {
    throw "Loader log not found: $log"
}

$cleanVersion = $Version -replace '^v', ''
$parts = @($cleanVersion -split '\.')
if ($parts.Count -lt 2) {
    throw "Version must look like v0.10.1 or 0.10.1. Received: $Version"
}

# Preserve existing archive naming conventions:
#   v0.9.6.1 -> completionist-v0961.txt
#   v0.10.1  -> completionist-v101.txt
if ($parts[0] -eq '0' -and [int]$parts[1] -ge 10) {
    $versionToken = ($parts[1..($parts.Count - 1)] -join '')
}
else {
    $versionToken = ($parts -join '')
}

$fileName = "completionist-v$versionToken.txt"
$outDir = Join-Path $repo 'archive\field-logs'
$out = Join-Path $outDir $fileName
$relativeOut = "archive/field-logs/$fileName"
$pattern = "CompletionistMap v$cleanVersion"

New-Item -ItemType Directory -Force $outDir | Out-Null

$lines = Select-String $log -Pattern $pattern |
    ForEach-Object { $_.Line }

@(
    "=== Completionist Map v$cleanVersion ==="
    "Matches: $($lines.Count)"
    ''
    $lines
) | Set-Content -Path $out -Encoding UTF8

Write-Host "Saved test log: $out"
Write-Host "Matches: $($lines.Count)"

& git add -- $relativeOut
if ($LASTEXITCODE -ne 0) {
    throw 'git add failed for the exported field log.'
}

& git diff --cached --quiet -- $relativeOut
$hasChanges = $LASTEXITCODE -ne 0

if (-not $hasChanges) {
    Write-Host 'Field log is unchanged. Nothing to commit.'
    exit 0
}

$commitMessage = "Archive Completionist v$cleanVersion field test log"
& git commit -m $commitMessage -- $relativeOut
if ($LASTEXITCODE -ne 0) {
    throw 'git commit failed for the exported field log.'
}

& git push $Remote $branch
if ($LASTEXITCODE -ne 0) {
    throw "git push failed. The log commit exists locally on branch '$branch'."
}

Write-Host "Pushed field log to $Remote/$branch"
