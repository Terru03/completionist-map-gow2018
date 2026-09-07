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
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before building the Raven UI visual clone.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$pythonScript = Join-Path $PSScriptRoot 'build-raven-ui-visual-clone.py'
if (-not (Test-Path -LiteralPath $pythonScript -PathType Leaf)) {
    throw "Missing builder: $pythonScript"
}
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$work = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.4\raven-ui-visual-clone'
$outRel = 'archive/field-logs/completionist-v104-raven-ui-visual-clone.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
New-Item -ItemType Directory -Force -Path $work, (Split-Path $out -Parent) | Out-Null

& $python.Source -m py_compile $pythonScript
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed for Raven visual-clone builder.' }

& $python.Source $pythonScript --game-root $GameRoot --work-dir $work --output $out
if ($LASTEXITCODE -ne 0) { throw 'Offline Raven visual-chain WAD/DCB build failed.' }

$gowTool = Join-Path $env:LOCALAPPDATA 'CompletionistMap\tools\GOWTool-v0.1.3-alpha\GOWTool.exe'
$gowToolSha = 'C1B0F3C7FB9DD2B26AE7EF4AC377308761FD3C7AFB21DAC7E4BEE20160A0008B'
if (-not (Test-Path -LiteralPath $gowTool -PathType Leaf)) {
    throw "GOWTool missing: $gowTool"
}
if ((Get-FileHash -LiteralPath $gowTool -Algorithm SHA256).Hash -ne $gowToolSha) {
    throw 'GOWTool SHA256 does not match the pinned v0.1.3-alpha binary.'
}

$ruiDds = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.2\r_ui-dds'
$stockDiffuse = Join-Path $ruiDds 'TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC.dds'
$stockEmissive = Join-Path $ruiDds 'TX_mapmarker_docklocation_emissive_FCC664130951154C.dds'
if (-not (Test-Path -LiteralPath $stockDiffuse -PathType Leaf) -or
    -not (Test-Path -LiteralPath $stockEmissive -PathType Leaf)) {
    Write-Host 'Stock r_ui DDS extraction missing. Re-extracting locally...'
    Remove-Item -LiteralPath $ruiDds -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $ruiDds | Out-Null
    $toolDir = Split-Path -Parent $gowTool
    $rUiWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
    Push-Location $toolDir
    try {
        & $gowTool wad -p $rUiWad -o $ruiDds -t -d
        $extractExit = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($extractExit -ne 0) { throw "GOWTool texture extraction failed with exit code $extractExit." }
}
foreach ($required in @($stockDiffuse, $stockEmissive)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required stock DDS missing after extraction: $required"
    }
}

$ravenPng = Join-Path $repo 'assets\icons\concepts\raven_concept_master.png'
if (-not (Test-Path -LiteralPath $ravenPng -PathType Leaf)) {
    throw "Raven artwork missing: $ravenPng"
}

function Get-DdsMetadata {
    param([Parameter(Mandatory=$true)][string]$Path)

    $fs = [System.IO.File]::OpenRead($Path)
    try {
        $br = New-Object System.IO.BinaryReader($fs)
        if ($br.ReadUInt32() -ne 0x20534444) { throw "Not a DDS file: $Path" }
        if ($br.ReadUInt32() -ne 124) { throw "Unexpected DDS header in $Path" }
        $null = $br.ReadUInt32()
        $height = [int]$br.ReadUInt32()
        $width = [int]$br.ReadUInt32()
        $null = $br.ReadUInt32()
        $null = $br.ReadUInt32()
        $mips = [int]$br.ReadUInt32()
        if ($mips -lt 1) { $mips = 1 }

        $fs.Position = 84
        $fourCCValue = $br.ReadUInt32()
        $fourCC = [Text.Encoding]::ASCII.GetString([BitConverter]::GetBytes($fourCCValue))
        $dxgi = $null
        $format = switch ($fourCC) {
            'DXT1' { 'BC1_UNORM' }
            'DXT3' { 'BC2_UNORM' }
            'DXT5' { 'BC3_UNORM' }
            'ATI1' { 'BC4_UNORM' }
            'BC4U' { 'BC4_UNORM' }
            'ATI2' { 'BC5_UNORM' }
            'BC5U' { 'BC5_UNORM' }
            'DX10' {
                $fs.Position = 128
                $dxgi = [int]$br.ReadUInt32()
                switch ($dxgi) {
                    28 { 'R8G8B8A8_UNORM' }
                    29 { 'R8G8B8A8_UNORM_SRGB' }
                    71 { 'BC1_UNORM' }
                    72 { 'BC1_UNORM_SRGB' }
                    74 { 'BC2_UNORM' }
                    75 { 'BC2_UNORM_SRGB' }
                    77 { 'BC3_UNORM' }
                    78 { 'BC3_UNORM_SRGB' }
                    80 { 'BC4_UNORM' }
                    81 { 'BC4_SNORM' }
                    83 { 'BC5_UNORM' }
                    84 { 'BC5_SNORM' }
                    98 { 'BC7_UNORM' }
                    99 { 'BC7_UNORM_SRGB' }
                    default { $null }
                }
            }
            default { $null }
        }
        if (-not $format) {
            throw "Unsupported DDS format in $Path (FourCC='$fourCC', DXGI='$dxgi')."
        }
        [pscustomobject]@{
            Width = $width
            Height = $height
            Mips = $mips
            FourCC = $fourCC
            Dxgi = $dxgi
            Format = $format
        }
    }
    finally {
        $fs.Dispose()
    }
}

$diffMeta = Get-DdsMetadata -Path $stockDiffuse
$emisMeta = Get-DdsMetadata -Path $stockEmissive
if ($diffMeta.Width -ne 148 -or $diffMeta.Height -ne 148 -or $diffMeta.Format -ne 'BC7_UNORM_SRGB') {
    throw 'Unexpected stock Dock diffuse metadata.'
}
if ($emisMeta.Width -ne 148 -or $emisMeta.Height -ne 148 -or $emisMeta.Format -ne 'BC1_UNORM') {
    throw 'Unexpected stock Dock emissive metadata.'
}

$dxRoot = Join-Path $env:LOCALAPPDATA 'CompletionistMap\tools\DirectXTex-may2026'
$texconv = Join-Path $dxRoot 'texconv.exe'
$texconvUrl = 'https://github.com/microsoft/DirectXTex/releases/download/may2026/texconv.exe'
$texconvSha = 'DCFDEC10244E02CF5037FBA089C55FB7E1326B1C8181742D77D15FA5CB5EEF06'
New-Item -ItemType Directory -Force -Path $dxRoot | Out-Null
if (-not (Test-Path -LiteralPath $texconv -PathType Leaf)) {
    Write-Host 'Downloading pinned DirectXTex texconv (May 2026)...'
    Invoke-WebRequest -Uri $texconvUrl -OutFile $texconv -UseBasicParsing
}
if ((Get-FileHash -LiteralPath $texconv -Algorithm SHA256).Hash -ne $texconvSha) {
    throw 'texconv SHA256 does not match the pinned May 2026 binary.'
}

$packRoot = Join-Path $work 'texpack'
$diffTemp = Join-Path $packRoot 'diffuse'
$emisTemp = Join-Path $packRoot 'emissive'
$inputDir = Join-Path $packRoot 'completionist_v104_raven_map'
Remove-Item -LiteralPath $packRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $diffTemp, $emisTemp, $inputDir | Out-Null

function Convert-RavenDds {
    param(
        [Parameter(Mandatory=$true)]$Meta,
        [Parameter(Mandatory=$true)][string]$TempDir,
        [Parameter(Mandatory=$true)][string]$TargetName
    )

    & $texconv -nologo -y -w $Meta.Width -h $Meta.Height -m $Meta.Mips -f $Meta.Format -o $TempDir $ravenPng
    if ($LASTEXITCODE -ne 0) { throw "texconv failed for $TargetName" }
    $generated = Join-Path $TempDir 'raven_concept_master.dds'
    if (-not (Test-Path -LiteralPath $generated -PathType Leaf)) {
        throw "texconv output missing: $generated"
    }
    $target = Join-Path $inputDir $TargetName
    Move-Item -LiteralPath $generated -Destination $target -Force
    $actual = Get-DdsMetadata -Path $target
    foreach ($prop in @('Width','Height','Mips','Format')) {
        if ($actual.$prop -ne $Meta.$prop) {
            throw "Generated DDS metadata mismatch for $TargetName at $prop."
        }
    }
    return $target
}

$diffName = 'TX_completionist_raven_map_diffuse_19A41F00834C19F3.dds'
$emisName = 'TX_completionist_raven_map_emissive_63F1E18FF93B9037.dds'
$diffDds = Convert-RavenDds -Meta $diffMeta -TempDir $diffTemp -TargetName $diffName
$emisDds = Convert-RavenDds -Meta $emisMeta -TempDir $emisTemp -TargetName $emisName

$toolDir = Split-Path -Parent $gowTool
Push-Location $toolDir
try {
    & $gowTool texpack -i -p $inputDir
    $packExit = $LASTEXITCODE
}
finally {
    Pop-Location
}
if ($packExit -ne 0) { throw "GOWTool texpack build failed with exit code $packExit." }

$builtPack = Join-Path $packRoot 'completionist_v104_raven_map.texpack'
$builtToc = Join-Path $packRoot 'completionist_v104_raven_map.texpack.toc'
foreach ($required in @($builtPack, $builtToc)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Expected texpack output missing: $required"
    }
}

$report = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
$report.texpack_contract.status = 'BUILT_OFFLINE'
$report | Add-Member -NotePropertyName texpack_validation -NotePropertyValue ([pscustomobject]@{
    pack = [pscustomobject]@{
        path = $builtPack
        bytes = (Get-Item -LiteralPath $builtPack).Length
        sha256 = (Get-FileHash -LiteralPath $builtPack -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    toc = [pscustomobject]@{
        path = $builtToc
        bytes = (Get-Item -LiteralPath $builtToc).Length
        sha256 = (Get-FileHash -LiteralPath $builtToc -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    diffuse = [pscustomobject]@{
        path = $diffDds
        bytes = (Get-Item -LiteralPath $diffDds).Length
        sha256 = (Get-FileHash -LiteralPath $diffDds -Algorithm SHA256).Hash.ToLowerInvariant()
        width = $diffMeta.Width
        height = $diffMeta.Height
        mips = $diffMeta.Mips
        format = $diffMeta.Format
        file_hash = '19A41F00834C19F3'
    }
    emissive = [pscustomobject]@{
        path = $emisDds
        bytes = (Get-Item -LiteralPath $emisDds).Length
        sha256 = (Get-FileHash -LiteralPath $emisDds -Algorithm SHA256).Hash.ToLowerInvariant()
        width = $emisMeta.Width
        height = $emisMeta.Height
        mips = $emisMeta.Mips
        format = $emisMeta.Format
        file_hash = '63F1E18FF93B9037'
    }
    gowtool_sha256 = $gowToolSha.ToLowerInvariant()
    texconv_sha256 = $texconvSha.ToLowerInvariant()
    installed_into_game = $false
})

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($out, ($report | ConvertTo-Json -Depth 30) + [Environment]::NewLine, $utf8NoBom)

# Reconfirm the game source files still have the exact researched hashes.
$wadSource = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$dcbSource = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_ui.dcb'
if ((Get-FileHash -LiteralPath $wadSource -Algorithm SHA256).Hash -ne '92294D218855EE4FBD06F66A2071F61C6B831240AAF41A59A3B7B8168C0F4B04') {
    throw 'Game r_ui.wad changed during offline build.'
}
if ((Get-FileHash -LiteralPath $dcbSource -Algorithm SHA256).Hash -ne '21EC389426FB8B6A7F89C8FFF6751522AA7DED13324E041B885DD7A490C2D14A') {
    throw 'Game wad_r_ui.dcb changed during offline build.'
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Raven visual-clone report unchanged; nothing to commit.'
    }
    else {
        git commit -m 'Archive Raven UI visual clone validation' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) {
            throw "git push failed; the validation commit remains local on '$branch'."
        }
        Write-Host "Pushed Raven UI visual-clone validation to $Remote/$branch"
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Offline Raven UI visual clone build complete.'
Write-Host "Candidate WAD/DCB: $work"
Write-Host "Candidate texpack: $builtPack"
Write-Host 'Nothing was installed into God of War.'
Write-Host 'Stock DockPoint artwork and native Kratos/Omega remain untouched.'
