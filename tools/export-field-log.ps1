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

$versionToken = ($Version -replace '^v', '') -replace '\.', ''
$outDir = Join-Path $repo 'archive\field-logs'
$out = Join-Path $outDir ("completionist-v{0}.txt" -f $versionToken)
$relativeOut = [IO.Path]::GetRelativePath($repo, $out).Replace('\\', '/')
$pattern = "CompletionistMap v$($Version -replace '^v', '')"

New-Item -ItemType Directory -Force $outDir | Out-Null

$lines = Select-String $log -Pattern $pattern |
    ForEach-Object { $_.Line }

@(
    "=== Completionist Map v$($Version -replace '^v', '') ==="
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

$commitMessage = "Archive Completionist v$($Version -replace '^v', '') field test log"
& git commit -m $commitMessage -- $relativeOut
if ($LASTEXITCODE -ne 0) {
    throw 'git commit failed for the exported field log.'
}

& git push $Remote $branch
if ($LASTEXITCODE -ne 0) {
    throw "git push failed. The log commit exists locally on branch '$branch'."
}

Write-Host "Pushed field log to $Remote/$branch"
