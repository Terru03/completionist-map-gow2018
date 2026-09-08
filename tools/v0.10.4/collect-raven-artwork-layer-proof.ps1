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
$pack = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack'
$toc = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack.toc'
$manifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-layer\active.json'
$outRel = 'archive/field-logs/completionist-v104-raven-artwork-layer-runtime.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('Completionist Map v0.10.4 isolated Raven artwork-layer runtime capture')
$lines.Add('Captured UTC: ' + [DateTime]::UtcNow.ToString('o'))
$lines.Add('Game process running while captured: ' + [bool](Get-Process -Name GoW -ErrorAction SilentlyContinue))
$lines.Add('mapmaster.dcb: ' + (HashOrMissing $mapmaster))
$lines.Add('r_ui.wad: ' + (HashOrMissing $ruiWad))
$lines.Add('wad_r_ui.dcb: ' + (HashOrMissing $ruiDcb))
$lines.Add('mapmenu.lua: ' + (HashOrMissing $mapmenu))
$lines.Add('boot-options.json: ' + (HashOrMissing $boot))
$lines.Add('raven texpack: ' + (HashOrMissing $pack))
$lines.Add('raven texpack toc: ' + (HashOrMissing $toc))
$lines.Add('')
$lines.Add('ACTIVE ARTWORK-LAYER MANIFEST')
if (Test-Path -LiteralPath $manifest -PathType Leaf) {
    $lines.AddRange([string[]](Get-Content -LiteralPath $manifest))
} else {
    $lines.Add('<not active / manifest missing>')
}
$lines.Add('')
$lines.Add('BOOT PATCH TEXPACKS')
if (Test-Path -LiteralPath $boot -PathType Leaf) {
    try {
        $bootObj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
        foreach ($entry in @($bootObj.'patch-texpacks')) { $lines.Add([string]$entry) }
    } catch {
        $lines.Add('<boot parse error: ' + $_.Exception.Message + '>')
    }
}
$lines.Add('')
$lines.Add('RELEVANT LOADER LOG')
if (-not (Test-Path -LiteralPath $loaderLog -PathType Leaf)) {
    $lines.Add('<loader_log.txt missing>')
} else {
    $tail = @(Get-Content -LiteralPath $loaderLog | Select-Object -Last 12000)
    $regex = @(
        'CompletionistMap v0\.10\.4-raven-artwork',
        'CompletionistMap v0\.10\.4-raven-registered-runtime',
        'CompletionistMap v0\.10\.3-native',
        '\[error\]',
        '\[critical\]',
        '\[fatal\]',
        'bad argument',
        'exception'
    ) -join '|'
    $matches = @($tail | Where-Object { $_ -match $regex })
    if ($matches.Count -eq 0) {
        $lines.Add('<no matching lines in last 12000 loader-log lines>')
        $lines.AddRange([string[]]($tail | Select-Object -Last 250))
    } else {
        $lines.AddRange([string[]]($matches | Select-Object -Last 1500))
    }
}
$lines.Add('')
$lines.Add('INTERPRETATION TARGETS')
$lines.Add('ART_RESULT active=true with goName containing completionistraven proves the corrected dedicated map GO still instantiates with the texpack active.')
$lines.Add('Visual success additionally requires the user to observe Raven artwork on that map marker while real boat docks remain stock.')
$lines.Add('NATIVE_RAVEN_PROMPT_REFRESH / PROMPT_SETTLED lines verify the asynchronous compass-prompt race fix.')
$lines.Add('HUD compass artwork remains DockPoint by design at this stage.')
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
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for artwork-layer runtime report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven artwork layer runtime' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for artwork-layer runtime report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for artwork-layer runtime report.' }
    } else {
        Write-Host 'Artwork-layer runtime report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host 'No God of War files were modified.'
