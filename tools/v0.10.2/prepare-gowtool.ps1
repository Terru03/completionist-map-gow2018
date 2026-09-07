param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'

$repo = (& git rev-parse --show-toplevel).Trim()
if (-not $repo) { throw 'Run this script from inside the Completionist Map Git repository.' }

$branch = (& git branch --show-current).Trim()
if (-not $branch) { throw 'Detached HEAD is not supported.' }

if (-not (Test-Path $GameRoot)) { throw "God of War root not found: $GameRoot" }

$toolRoot = Join-Path $env:LOCALAPPDATA 'CompletionistMap\tools\GOWTool-v0.1.3-alpha'
$exe = Join-Path $toolRoot 'GOWTool.exe'
$url = 'https://github.com/kainotoa/GOWTool/releases/download/v0.1.3-alpha/GOWTool.exe'

New-Item -ItemType Directory -Force $toolRoot | Out-Null

if (-not (Test-Path $exe)) {
    Write-Host 'Downloading GOWTool v0.1.3-alpha for God of War 2018 PC...'
    Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
}

if (-not (Test-Path $exe)) { throw 'GOWTool download did not produce the expected executable.' }

$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
$size = (Get-Item -LiteralPath $exe).Length

$outDir = Join-Path $repo 'archive\field-logs'
$out = Join-Path $outDir 'completionist-v102-gowtool-probe.txt'
New-Item -ItemType Directory -Force $outDir | Out-Null

Push-Location $toolRoot
try {
    $settingsOutput = & $exe settings -g $GameRoot 2>&1 | Out-String
    $settingsExit = $LASTEXITCODE

    $helpOutput = & $exe --help 2>&1 | Out-String
    $helpExit = $LASTEXITCODE

    $texpackHelp = & $exe texpack --help 2>&1 | Out-String
    $texpackHelpExit = $LASTEXITCODE

    $wadHelp = & $exe wad --help 2>&1 | Out-String
    $wadHelpExit = $LASTEXITCODE
}
finally {
    Pop-Location
}

$lines = @(
    '=== Completionist Map v0.10.2 GOWTool probe ==='
    "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    "Branch: $branch"
    "GameRoot: $GameRoot"
    "Tool: GOWTool v0.1.3-alpha PC"
    "ToolPath: $exe"
    "DownloadURL: $url"
    "SizeBytes: $size"
    "SHA256: $hash"
    ''
    "settings exit: $settingsExit"
    $settingsOutput.TrimEnd()
    ''
    "root help exit: $helpExit"
    $helpOutput.TrimEnd()
    ''
    "texpack help exit: $texpackHelpExit"
    $texpackHelp.TrimEnd()
    ''
    "wad help exit: $wadHelpExit"
    $wadHelp.TrimEnd()
    ''
    'Notes:'
    '- The executable is stored under LocalAppData, not in the Git repository.'
    '- This probe does not modify God of War game files.'
    '- The settings command only writes GOWTool local configuration pointing at the game directory.'
)

$lines | Set-Content -LiteralPath $out -Encoding UTF8
Write-Host "Saved GOWTool probe: $out"
Write-Host "SHA256: $hash"
Write-Host "settings exit: $settingsExit"
Write-Host "texpack help exit: $texpackHelpExit"
Write-Host "wad help exit: $wadHelpExit"

if ($settingsExit -ne 0) { throw 'GOWTool settings command failed. Probe report was still written.' }
if ($texpackHelpExit -ne 0) { throw 'GOWTool texpack help failed. Probe report was still written.' }
if ($wadHelpExit -ne 0) { throw 'GOWTool wad help failed. Probe report was still written.' }

$relativeOut = 'archive/field-logs/completionist-v102-gowtool-probe.txt'
& git add -- $relativeOut
if ($LASTEXITCODE -ne 0) { throw 'git add failed for the GOWTool probe.' }

& git diff --cached --quiet -- $relativeOut
if ($LASTEXITCODE -eq 0) {
    Write-Host 'GOWTool probe is unchanged. Nothing to commit.'
    exit 0
}

& git commit -m 'Archive v0.10.2 GOWTool probe' -- $relativeOut
if ($LASTEXITCODE -ne 0) { throw 'git commit failed for the GOWTool probe.' }

& git push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw "git push failed. The probe commit exists locally on '$branch'." }

Write-Host "Pushed GOWTool probe to $Remote/$branch"
