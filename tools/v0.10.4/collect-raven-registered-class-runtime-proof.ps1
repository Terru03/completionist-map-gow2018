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
$manifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-registered-class-runtime\active.json'
$outRel = 'archive/field-logs/completionist-v104-raven-registered-class-runtime.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('Completionist Map v0.10.4 corrected registered Raven class runtime capture')
$lines.Add('Captured UTC: ' + [DateTime]::UtcNow.ToString('o'))
$lines.Add('Game process running while captured: ' + [bool](Get-Process -Name GoW -ErrorAction SilentlyContinue))
$lines.Add('mapmaster.dcb: ' + (HashOrMissing $mapmaster))
$lines.Add('r_ui.wad: ' + (HashOrMissing $ruiWad))
$lines.Add('wad_r_ui.dcb: ' + (HashOrMissing $ruiDcb))
$lines.Add('mapmenu.lua: ' + (HashOrMissing $mapmenu))
$lines.Add('boot-options.json: ' + (HashOrMissing $boot))
$lines.Add('')
$lines.Add('ACTIVE REGISTERED-RUNTIME MANIFEST')
if (Test-Path -LiteralPath $manifest -PathType Leaf) {
    $lines.AddRange([string[]](Get-Content -LiteralPath $manifest))
} else {
    $lines.Add('<not active / manifest missing>')
}
$lines.Add('')
$lines.Add('RELEVANT LOADER LOG')
if (-not (Test-Path -LiteralPath $loaderLog -PathType Leaf)) {
    $lines.Add('<loader_log.txt missing>')
} else {
    $tail = @(Get-Content -LiteralPath $loaderLog | Select-Object -Last 15000)
    $regex = @(
        'CompletionistMap v0\.10\.4-raven-registered-runtime',
        'CompletionistMap v0\.10\.3-native',
        'goMapIconCompletionistRaven',
        'gomapiconcompletionistraven',
        '\[error\]',
        '\[critical\]',
        '\[fatal\]',
        'bad argument',
        'exception',
        'assert',
        'crash'
    ) -join '|'
    $matches = @($tail | Where-Object { $_ -match $regex })
    if ($matches.Count -eq 0) {
        $lines.Add('<no matching lines in last 15000 loader-log lines>')
        $lines.AddRange([string[]]($tail | Select-Object -Last 300))
    } else {
        $lines.AddRange([string[]]($matches | Select-Object -Last 1500))
    }
}
$lines.Add('')
$lines.Add('FIELD-PROOF INTERPRETATION TARGETS')
$lines.Add('Success requires REGISTERED_RESULT active=true, stable repeated map opens, and no loader/runtime fatal error.')
$lines.Add('A dedicated GO name containing completionistraven is strongest proof. A Dock-looking picture alone is not failure at this gate because no custom texpack is loaded.')
$lines.Add('')
$lines.Add('NOTE')
$lines.Add('Read-only collector. No God of War files, saves, marker states, progression values, or boot options are changed.')

$normalised = @($lines | ForEach-Object { ([string]$_).TrimEnd() })
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out, $normalised, $utf8)
Write-Host "Saved: $out"

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for registered Raven runtime report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven registered class runtime' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for registered Raven runtime report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for registered Raven runtime report.' }
    } else {
        Write-Host 'Registered Raven runtime report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host 'No God of War files were modified.'
