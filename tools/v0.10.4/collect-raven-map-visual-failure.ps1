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
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

function HashOrMissing([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '<missing>' }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$game = [IO.Path]::GetFullPath($GameRoot)
$loaderLog = Join-Path $game 'mods\loader_log.txt'
$mapmaster = Join-Path $game 'exec\dc\pc_le\mapmaster.dcb'
$ruiWad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$ruiDcb = Join-Path $game 'exec\dc\pc_le\wad_r_ui.dcb'
$mapmenu = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$boot = Join-Path $game 'exec\boot-options.json'
$stateManifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-map-visual-proof\active.json'

$outRel = 'archive/field-logs/completionist-v104-raven-map-visual-runtime-failure.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('Completionist Map v0.10.4 Raven map visual runtime failure capture')
$lines.Add('Captured UTC: ' + [DateTime]::UtcNow.ToString('o'))
$lines.Add('Game process running while captured: ' + [bool](Get-Process -Name GoW -ErrorAction SilentlyContinue))
$lines.Add('')
$lines.Add('CURRENT FILE HASHES')
$lines.Add('mapmaster.dcb: ' + (HashOrMissing $mapmaster))
$lines.Add('r_ui.wad: ' + (HashOrMissing $ruiWad))
$lines.Add('wad_r_ui.dcb: ' + (HashOrMissing $ruiDcb))
$lines.Add('mapmenu.lua: ' + (HashOrMissing $mapmenu))
$lines.Add('boot-options.json: ' + (HashOrMissing $boot))
$lines.Add('')

$lines.Add('ACTIVE VISUAL PROOF MANIFEST')
if (Test-Path -LiteralPath $stateManifest -PathType Leaf) {
    $lines.AddRange([string[]](Get-Content -LiteralPath $stateManifest))
} else {
    $lines.Add('<not active / manifest missing>')
}
$lines.Add('')

$lines.Add('RELEVANT LOADER LOG')
if (-not (Test-Path -LiteralPath $loaderLog -PathType Leaf)) {
    $lines.Add('<loader_log.txt missing>')
} else {
    $all = Get-Content -LiteralPath $loaderLog
    $tail = @($all | Select-Object -Last 6000)
    $patterns = @(
        'CompletionistMap v0\.10\.4-raven-map-visual',
        'CompletionistMap v0\.10\.3-native',
        'CompletionistMap v0\.10\.1.*MAP_PIN_CREATE',
        'CompletionistMap v0\.10\.1.*ICON_',
        '\[error\]',
        '\[critical\]',
        '\[fatal\]',
        'assert',
        'exception'
    )
    $regex = ($patterns -join '|')
    $matches = @($tail | Where-Object { $_ -match $regex })
    if ($matches.Count -eq 0) {
        $lines.Add('<no matching lines in last 6000 loader-log lines>')
        $lines.Add('')
        $lines.Add('LAST 120 LOADER LOG LINES (fallback)')
        $lines.AddRange([string[]]($tail | Select-Object -Last 120))
    } else {
        # Keep the report bounded while preserving the latest proof sequence.
        $lines.AddRange([string[]]($matches | Select-Object -Last 600))
    }
}
$lines.Add('')
$lines.Add('NOTE')
$lines.Add('This collector is read-only with respect to God of War. It does not roll back or install any proof.')

# Loader lines can contain harmless trailing spaces. Normalise them before
# git diff --check so captured runtime evidence can always be archived.
$normalisedLines = @($lines | ForEach-Object { ([string]$_).TrimEnd() })
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out, $normalisedLines, $utf8)
Write-Host "Saved: $out"

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for runtime failure report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Runtime failure report unchanged; nothing to commit.'
    } else {
        git commit -m 'Archive Raven map visual runtime failure' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for runtime failure report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for runtime failure report.' }
        Write-Host "Pushed runtime failure evidence to $Remote/$branch"
    }
}
finally { Pop-Location }

Write-Host 'No God of War files were modified.'
