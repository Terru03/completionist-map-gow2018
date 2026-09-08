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

function Hex64([UInt64]$Value) { return ('{0:X16}' -f $Value) }

function Read-TargetTexInfos {
    param([Parameter(Mandatory=$true)][string]$Path)
    $targets = @{
        ([UInt64]::Parse('19A41F00834C19F3',[Globalization.NumberStyles]::HexNumber)) = 'diffuse'
        ([UInt64]::Parse('63F1E18FF93B9037',[Globalization.NumberStyles]::HexNumber)) = 'emissive'
    }
    $fs = [IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
    try {
        $br = New-Object IO.BinaryReader($fs)
        $fs.Position = 0x2C
        $count = $br.ReadUInt32()
        $fs.Position = 0x38
        $rows = @()
        for ($i=0; $i -lt $count; $i++) {
            $fileHash = [UInt64]$br.ReadUInt64()
            $userHash = [UInt64]$br.ReadUInt64()
            $blockInfoOff = [UInt64]$br.ReadUInt64()
            if ($targets.ContainsKey($fileHash)) {
                $rows += [pscustomobject]@{
                    Label = $targets[$fileHash]
                    Index = $i
                    FileHash = $fileHash
                    UserHash = $userHash
                    BlockInfoOff = $blockInfoOff
                }
            }
        }
        return $rows
    }
    finally { $fs.Dispose() }
}

$game = [IO.Path]::GetFullPath($GameRoot)
$loaderLog = Join-Path $game 'mods\loader_log.txt'
$boot = Join-Path $game 'exec\boot-options.json'
$ruiWad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$ruiDcb = Join-Path $game 'exec\dc\pc_le\wad_r_ui.dcb'
$mapmaster = Join-Path $game 'exec\dc\pc_le\mapmaster.dcb'
$patchPack = Join-Path $game 'exec\patch\pc_le\completionist_v104_raven_map.texpack'
$patchToc = Join-Path $game 'exec\patch\pc_le\completionist_v104_raven_map.texpack.toc'
$manifest = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state\v0.10.4-raven-texpack-userhash-binding\active.json'

$outRel = 'archive/field-logs/completionist-v104-raven-texpack-binding-runtime.txt'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('Completionist Map v0.10.4 Raven texpack user-hash binding runtime capture')
$lines.Add('Captured UTC: ' + [DateTime]::UtcNow.ToString('o'))
$lines.Add('Game process running while captured: ' + [bool](Get-Process -Name GoW -ErrorAction SilentlyContinue))
$lines.Add('mapmaster.dcb: ' + (HashOrMissing $mapmaster))
$lines.Add('r_ui.wad: ' + (HashOrMissing $ruiWad))
$lines.Add('wad_r_ui.dcb: ' + (HashOrMissing $ruiDcb))
$lines.Add('patch texpack: ' + (HashOrMissing $patchPack))
$lines.Add('patch toc: ' + (HashOrMissing $patchToc))
$lines.Add('')
$lines.Add('ACTIVE BINDING MANIFEST')
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
$lines.Add('TARGET TEXPACK ENTRIES')
if (Test-Path -LiteralPath $patchPack -PathType Leaf) {
    try {
        foreach ($row in @(Read-TargetTexInfos -Path $patchPack | Sort-Object Label)) {
            $lines.Add("$($row.Label): index=$($row.Index) fileHash=$(Hex64 $row.FileHash) userHash=$(Hex64 $row.UserHash) blockInfoOff=0x$('{0:X}' -f $row.BlockInfoOff)")
        }
    } catch {
        $lines.Add('<texpack parse error: ' + $_.Exception.Message + '>')
    }
} else {
    $lines.Add('<patch texpack missing>')
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
$lines.Add('INTERPRETATION')
$lines.Add('Expected custom diffuse userHash after binding: 7ABBBA793C03C741')
$lines.Add('Expected custom emissive userHash after binding: 15AD16D2A17DEB42')
$lines.Add('The dedicated Raven WAD contains stock-Dock embedded GPU fallback payload bytes; if the external stream does not bind, the marker can therefore appear as a lower-quality Dock icon.')
$lines.Add('Visual success requires user confirmation that the Raven map marker now shows the custom Raven artwork while real docks remain stock.')
$lines.Add('HUD compass artwork remains DockPoint by design at this stage.')
$lines.Add('')
$lines.Add('NOTE')
$lines.Add('Read-only collector. No God of War files, saves, marker states, progression values or boot options are changed.')

$normalised = @($lines | ForEach-Object { ([string]$_).TrimEnd() })
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($out,$normalised,$utf8)
Write-Host "Saved: $out"

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for Raven texpack binding runtime report.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive Raven texpack binding runtime' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for Raven texpack binding runtime report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for Raven texpack binding runtime report.' }
    } else {
        Write-Host 'Raven texpack binding runtime report unchanged; nothing to commit.'
    }
}
finally { Pop-Location }

Write-Host 'No God of War files were modified.'
