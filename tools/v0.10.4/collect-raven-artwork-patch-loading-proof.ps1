param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Wrong branch: $branch" }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

function HashOrMissing([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '<missing>' }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$game = [IO.Path]::GetFullPath($GameRoot)
$boot = Join-Path $game 'exec\boot-options.json'
$loader = Join-Path $game 'mods\loader_log.txt'
$patchPack = Join-Path $game 'exec\patch\pc_le\completionist_v104_raven_map.texpack'
$patchToc = Join-Path $game 'exec\patch\pc_le\completionist_v104_raven_map.texpack.toc'
$legacyPack = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack'
$legacyToc = Join-Path $game 'exec\wad\pc_le\completionist_v104_raven_map.texpack.toc'
$manifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-artwork-patch-loading\active.json'
$outRel = 'archive/field-logs/completionist-v104-raven-artwork-patch-loading-runtime.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('Completionist Map v0.10.4 Raven artwork patch-loading runtime capture')
$lines.Add('Captured UTC: ' + [DateTime]::UtcNow.ToString('o'))
$lines.Add('Game process running while captured: ' + [bool](Get-Process -Name GoW -ErrorAction SilentlyContinue))
$lines.Add('boot-options.json: ' + (HashOrMissing $boot))
$lines.Add('exec/patch texpack: ' + (HashOrMissing $patchPack))
$lines.Add('exec/patch toc: ' + (HashOrMissing $patchToc))
$lines.Add('legacy exec/wad texpack: ' + (HashOrMissing $legacyPack))
$lines.Add('legacy exec/wad toc: ' + (HashOrMissing $legacyToc))
$lines.Add('')
$lines.Add('PATCH-LOADING MANIFEST')
if (Test-Path -LiteralPath $manifest -PathType Leaf) {
    $lines.AddRange([string[]](Get-Content -LiteralPath $manifest))
} else {
    $lines.Add('<missing>')
}
$lines.Add('')
$lines.Add('BOOT PATCH TEXPACKS')
if (Test-Path -LiteralPath $boot -PathType Leaf) {
    try {
        $obj = Get-Content -LiteralPath $boot -Raw | ConvertFrom-Json
        foreach ($entry in @($obj.'patch-texpacks')) { $lines.Add([string]$entry) }
    } catch { $lines.Add('<boot parse failed: ' + $_.Exception.Message + '>') }
}
$lines.Add('')
$lines.Add('RELEVANT LOADER LOG')
if (Test-Path -LiteralPath $loader -PathType Leaf) {
    $tail = @(Get-Content -LiteralPath $loader | Select-Object -Last 12000)
    $regex = @(
        'CompletionistMap v0\.10\.4-raven-artwork',
        'CompletionistMap v0\.10\.4-raven-registered-runtime',
        'CompletionistMap v0\.10\.3-native',
        'texpack',
        '\[error\]',
        '\[critical\]',
        '\[fatal\]',
        'exception'
    ) -join '|'
    $matches = @($tail | Where-Object { $_ -match $regex })
    if ($matches.Count) { $lines.AddRange([string[]]($matches | Select-Object -Last 1500)) }
    else { $lines.Add('<no matching lines>') }
} else { $lines.Add('<loader_log.txt missing>') }
$lines.Add('')
$lines.Add('INTERPRETATION')
$lines.Add('Expected boot entry: ../../patch/pc_le/completionist_v104_raven_map')
$lines.Add('Expected patch texpack SHA256: a224969576eb68b004a49e2baabe7a13957f5bfe12d8fd4e0bf87e04e2dd1fc1')
$lines.Add('Expected legacy exec/wad copies: missing after migration.')
$lines.Add('Visual success still requires user confirmation that Raven artwork replaced the low-quality Dock fallback only on the dedicated Raven map marker.')
$lines.Add('')
$lines.Add('NOTE')
$lines.Add('Read-only collector. No game files, saves, marker states or progression values are modified.')

$normalised = @($lines | ForEach-Object { ([string]$_).TrimEnd() })
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out, $normalised, $utf8)
Write-Host "Saved: $out"

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven artwork patch loading runtime' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    }
}
finally { Pop-Location }

Write-Host 'No God of War files were modified.'
