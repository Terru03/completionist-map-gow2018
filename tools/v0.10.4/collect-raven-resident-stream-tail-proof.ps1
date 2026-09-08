param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') { throw "Expected feat/v0.10.4-all-ravens, got '$branch'." }

function HashOrMissing([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '<missing>' }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$game = [IO.Path]::GetFullPath($GameRoot)
$loaderLog = Join-Path $game 'mods\loader_log.txt'
$wad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$dcb = Join-Path $game 'exec\dc\pc_le\wad_r_ui.dcb'
$mapmaster = Join-Path $game 'exec\dc\pc_le\mapmaster.dcb'
$pack = Join-Path $game 'exec\patch\pc_le\completionist_v104_raven_map.texpack'
$manifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-resident-stream-tail\active.json'
$outRel = 'archive/field-logs/completionist-v104-raven-resident-stream-tail-runtime.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('Completionist Map v0.10.4 Raven resident stream-tail runtime capture')
$lines.Add('Captured UTC: ' + [DateTime]::UtcNow.ToString('o'))
$lines.Add('Game process running while captured: ' + [bool](Get-Process -Name GoW -ErrorAction SilentlyContinue))
$lines.Add('r_ui.wad: ' + (HashOrMissing $wad))
$lines.Add('wad_r_ui.dcb: ' + (HashOrMissing $dcb))
$lines.Add('mapmaster.dcb: ' + (HashOrMissing $mapmaster))
$lines.Add('Raven patch texpack: ' + (HashOrMissing $pack))
$lines.Add('')
$lines.Add('ACTIVE STREAM-TAIL ARTWORK MANIFEST')
if (Test-Path -LiteralPath $manifest -PathType Leaf) {
    $lines.AddRange([string[]](Get-Content -LiteralPath $manifest))
} else {
    $lines.Add('<manifest missing>')
}
$lines.Add('')
$lines.Add('RELEVANT LOADER LOG')
if (Test-Path -LiteralPath $loaderLog -PathType Leaf) {
    $tail = @(Get-Content -LiteralPath $loaderLog | Select-Object -Last 12000)
    $regex = @(
        'CompletionistMap v0\.10\.4-raven-artwork',
        'CompletionistMap v0\.10\.4-raven-registered-runtime',
        'CompletionistMap v0\.10\.3-native',
        '\[error\]', '\[critical\]', '\[fatal\]', 'bad argument', 'exception'
    ) -join '|'
    $matches = @($tail | Where-Object { $_ -match $regex })
    if ($matches.Count) { $lines.AddRange([string[]]($matches | Select-Object -Last 1500)) }
    else { $lines.Add('<no matching loader-log lines>') }
} else {
    $lines.Add('<loader_log.txt missing>')
}
$lines.Add('')
$lines.Add('INTERPRETATION')
$lines.Add('User visual observation is authoritative. Expected MAP result: custom Raven artwork on mapiconcompletionistraven with no corrupted block striping.')
$lines.Add('HUD compass remains DockPoint by design and may still show boat Dock artwork.')
$lines.Add('Real Dock and Valkyrie resources should remain stock.')
$lines.Add('')
$lines.Add('NOTE')
$lines.Add('Read-only collector. It does not modify God of War files, saves, progression, boot options or marker state.')

$normalised = @($lines | ForEach-Object { ([string]$_).TrimEnd() })
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out, $normalised, $utf8)
Write-Host "Saved: $out"

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for resident stream-tail runtime report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven resident stream-tail runtime' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for resident stream-tail runtime report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for resident stream-tail runtime report.' }
    } else {
        Write-Host 'Resident stream-tail runtime report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host 'No God of War files were modified.'
