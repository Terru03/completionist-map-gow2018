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
$manifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-map-class-slot\active.json'
$outRel = 'archive/field-logs/completionist-v104-raven-map-class-slot-runtime.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('Completionist Map v0.10.4 Raven custom map-class GOPool-slot runtime capture')
$lines.Add('Captured UTC: ' + [DateTime]::UtcNow.ToString('o'))
$lines.Add('Game process running while captured: ' + [bool](Get-Process -Name GoW -ErrorAction SilentlyContinue))
$lines.Add('mapmaster.dcb: ' + (HashOrMissing $mapmaster))
$lines.Add('r_ui.wad: ' + (HashOrMissing $ruiWad))
$lines.Add('wad_r_ui.dcb: ' + (HashOrMissing $ruiDcb))
$lines.Add('mapmenu.lua: ' + (HashOrMissing $mapmenu))
$lines.Add('')
$lines.Add('ACTIVE SLOT MANIFEST')
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
    $tail = @(Get-Content -LiteralPath $loaderLog | Select-Object -Last 10000)
    $regex = @(
        'CompletionistMap v0\.10\.4-map-class-slot',
        'CompletionistMap v0\.10\.3-native',
        '\[error\]',
        '\[critical\]',
        '\[fatal\]',
        'bad argument',
        'exception'
    ) -join '|'
    $matches = @($tail | Where-Object { $_ -match $regex })
    if ($matches.Count -eq 0) {
        $lines.Add('<no matching lines in last 10000 loader-log lines>')
        $lines.AddRange([string[]]($tail | Select-Object -Last 180))
    } else {
        $lines.AddRange([string[]]($matches | Select-Object -Last 1000))
    }
}
$lines.Add('')
$lines.Add('NOTE')
$lines.Add('Read-only collector. No God of War files, saves, marker states, or progression values are changed.')

$normalised = @($lines | ForEach-Object { ([string]$_).TrimEnd() })
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out, $normalised, $utf8)
Write-Host "Saved: $out"

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for slot runtime report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven map class slot runtime' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for slot runtime report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for slot runtime report.' }
    } else {
        Write-Host 'Slot runtime report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host 'No God of War files were modified.'
