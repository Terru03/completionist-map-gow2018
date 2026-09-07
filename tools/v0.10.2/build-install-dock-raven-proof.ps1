param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'

$repo = (& git rev-parse --show-toplevel).Trim()
if (-not $repo) { throw 'Run this script from inside the Completionist Map Git repository.' }
$branch = (& git branch --show-current).Trim()
if (-not $branch) { throw 'Detached HEAD is not supported.' }
if ($branch -ne 'feat/v0.10.2-material-icons') {
    Write-Warning "Expected feat/v0.10.2-material-icons, current branch is '$branch'."
}
if (-not (Test-Path -LiteralPath $GameRoot)) { throw "God of War root not found: $GameRoot" }
if (Get-Process -Name 'GoW' -ErrorAction SilentlyContinue) {
    throw 'God of War is running. Close the game before installing the texture proof.'
}

$workRoot = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.2'
$ruiDds = Join-Path $workRoot 'r_ui-dds'
$diffuseOriginal = Join-Path $ruiDds 'TX_mapmarker_docklocation_diffuse_982BF904AB84F2CC.dds'
$emissiveOriginal = Join-Path $ruiDds 'TX_mapmarker_docklocation_emissive_FCC664130951154C.dds'
$ravenPng = Join-Path $repo 'assets\icons\concepts\raven_concept_master.png'
$gowTool = Join-Path $env:LOCALAPPDATA 'CompletionistMap\tools\GOWTool-v0.1.3-alpha\GOWTool.exe'

foreach ($required in @($diffuseOriginal, $emissiveOriginal, $ravenPng, $gowTool)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required file not found: $required" }
}

function Get-DdsMetadata {
    param([Parameter(Mandatory=$true)][string]$Path)

    $fs = [System.IO.File]::OpenRead($Path)
    try {
        $br = New-Object System.IO.BinaryReader($fs)
        if ($br.ReadUInt32() -ne 0x20534444) { throw "Not a DDS file: $Path" }
        $headerSize = $br.ReadUInt32()
        if ($headerSize -ne 124) { throw "Unexpected DDS header size $headerSize in $Path" }
        $null = $br.ReadUInt32() # flags
        $height = [int]$br.ReadUInt32()
        $width = [int]$br.ReadUInt32()
        $null = $br.ReadUInt32() # pitch/linear size
        $null = $br.ReadUInt32() # depth
        $mips = [int]$br.ReadUInt32()
        if ($mips -lt 1) { $mips = 1 }

        $fs.Position = 84
        $fourCCValue = $br.ReadUInt32()
        $fourCCBytes = [BitConverter]::GetBytes($fourCCValue)
        $fourCC = [Text.Encoding]::ASCII.GetString($fourCCBytes)

        $format = $null
        $dxgi = $null
        switch ($fourCC) {
            'DXT1' { $format = 'BC1_UNORM' }
            'DXT3' { $format = 'BC2_UNORM' }
            'DXT5' { $format = 'BC3_UNORM' }
            'ATI1' { $format = 'BC4_UNORM' }
            'BC4U' { $format = 'BC4_UNORM' }
            'ATI2' { $format = 'BC5_UNORM' }
            'BC5U' { $format = 'BC5_UNORM' }
            'DX10' {
                $fs.Position = 128
                $dxgi = [int]$br.ReadUInt32()
                $format = switch ($dxgi) {
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
                    87 { 'B8G8R8A8_UNORM' }
                    88 { 'B8G8R8X8_UNORM' }
                    91 { 'B8G8R8A8_UNORM_SRGB' }
                    93 { 'B8G8R8X8_UNORM_SRGB' }
                    95 { 'BC6H_UF16' }
                    96 { 'BC6H_SF16' }
                    98 { 'BC7_UNORM' }
                    99 { 'BC7_UNORM_SRGB' }
                    default { $null }
                }
            }
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

$diffMeta = Get-DdsMetadata -Path $diffuseOriginal
$emisMeta = Get-DdsMetadata -Path $emissiveOriginal

Write-Host "Dock diffuse:  $($diffMeta.Width)x$($diffMeta.Height), mips=$($diffMeta.Mips), format=$($diffMeta.Format)"
Write-Host "Dock emissive: $($emisMeta.Width)x$($emisMeta.Height), mips=$($emisMeta.Mips), format=$($emisMeta.Format)"

# Microsoft DirectXTex May 2026 texconv, pinned by release asset hash.
$dxRoot = Join-Path $env:LOCALAPPDATA 'CompletionistMap\tools\DirectXTex-may2026'
$texconv = Join-Path $dxRoot 'texconv.exe'
$texconvUrl = 'https://github.com/microsoft/DirectXTex/releases/download/may2026/texconv.exe'
$texconvSha256 = 'DCFDEC10244E02CF5037FBA089C55FB7E1326B1C8181742D77D15FA5CB5EEF06'
New-Item -ItemType Directory -Force $dxRoot | Out-Null
if (-not (Test-Path -LiteralPath $texconv)) {
    Write-Host 'Downloading Microsoft DirectXTex texconv (May 2026)...'
    Invoke-WebRequest -Uri $texconvUrl -OutFile $texconv -UseBasicParsing
}
$actualTexconvHash = (Get-FileHash -LiteralPath $texconv -Algorithm SHA256).Hash
if ($actualTexconvHash -ne $texconvSha256) {
    throw "texconv SHA256 mismatch. Expected $texconvSha256, got $actualTexconvHash"
}

$buildRoot = Join-Path $workRoot 'dock-raven-proof'
$diffTemp = Join-Path $buildRoot 'diffuse'
$emisTemp = Join-Path $buildRoot 'emissive'
$inputDir = Join-Path $buildRoot 'completionist_v102_dock_raven'
Remove-Item -LiteralPath $buildRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $diffTemp, $emisTemp, $inputDir | Out-Null

function Convert-RavenDds {
    param(
        [Parameter(Mandatory=$true)]$Meta,
        [Parameter(Mandatory=$true)][string]$OutDir,
        [Parameter(Mandatory=$true)][string]$TargetName
    )

    Write-Host "Creating $TargetName as $($Meta.Format)..."
    $output = & $texconv -nologo -y -w $Meta.Width -h $Meta.Height -m $Meta.Mips -f $Meta.Format -o $OutDir $ravenPng 2>&1
    if ($LASTEXITCODE -ne 0) {
        $output | ForEach-Object { Write-Host $_ }
        throw "texconv failed while creating $TargetName"
    }

    $generated = Join-Path $OutDir 'raven_concept_master.dds'
    if (-not (Test-Path -LiteralPath $generated)) { throw "texconv output missing: $generated" }
    $target = Join-Path $inputDir $TargetName
    Move-Item -LiteralPath $generated -Destination $target -Force
    return $target
}

$diffTargetName = 'TX_completionist_raven_dock_diffuse_982BF904AB84F2CC.dds'
$emisTargetName = 'TX_completionist_raven_dock_emissive_FCC664130951154C.dds'
$diffTarget = Convert-RavenDds -Meta $diffMeta -OutDir $diffTemp -TargetName $diffTargetName
$emisTarget = Convert-RavenDds -Meta $emisMeta -OutDir $emisTemp -TargetName $emisTargetName

# Verify generated files retained the requested size, mip count and format.
$diffGeneratedMeta = Get-DdsMetadata -Path $diffTarget
$emisGeneratedMeta = Get-DdsMetadata -Path $emisTarget
foreach ($check in @(
    @{ Label='diffuse'; Expected=$diffMeta; Actual=$diffGeneratedMeta },
    @{ Label='emissive'; Expected=$emisMeta; Actual=$emisGeneratedMeta }
)) {
    if ($check.Expected.Width -ne $check.Actual.Width -or
        $check.Expected.Height -ne $check.Actual.Height -or
        $check.Expected.Mips -ne $check.Actual.Mips -or
        $check.Expected.Format -ne $check.Actual.Format) {
        throw "Generated $($check.Label) DDS metadata does not match the stock texture."
    }
}

# GOWTool writes <input-folder-name>.texpack and .texpack.toc next to the input folder.
$gowToolRoot = Split-Path -Parent $gowTool
Push-Location $gowToolRoot
try {
    $packOutput = & $gowTool texpack -i -p $inputDir 2>&1
    $packExit = $LASTEXITCODE
}
finally {
    Pop-Location
}
if ($packExit -ne 0) {
    $packOutput | ForEach-Object { Write-Host $_ }
    throw "GOWTool texpack import failed with exit code $packExit"
}

$builtPack = Join-Path $buildRoot 'completionist_v102_dock_raven.texpack'
$builtToc = Join-Path $buildRoot 'completionist_v102_dock_raven.texpack.toc'
if (-not (Test-Path -LiteralPath $builtPack)) { throw "Built texpack not found: $builtPack" }
if (-not (Test-Path -LiteralPath $builtToc)) { throw "Built texpack TOC not found: $builtToc" }

$patchDir = Join-Path $GameRoot 'exec\patch\pc_le'
New-Item -ItemType Directory -Force $patchDir | Out-Null
$installedPack = Join-Path $patchDir 'completionist_v102_dock_raven.texpack'
$installedToc = Join-Path $patchDir 'completionist_v102_dock_raven.texpack.toc'
Copy-Item -LiteralPath $builtPack -Destination $installedPack -Force
Copy-Item -LiteralPath $builtToc -Destination $installedToc -Force

$bootPath = Join-Path $GameRoot 'exec\boot-options.json'
if (-not (Test-Path -LiteralPath $bootPath)) { throw "boot-options.json not found: $bootPath" }
$bootBackup = "$bootPath.completionist-v102-before-dock-raven.bak"
if (-not (Test-Path -LiteralPath $bootBackup)) {
    Copy-Item -LiteralPath $bootPath -Destination $bootBackup
}

$boot = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
$patchEntry = '../../patch/pc_le/completionist_v102_dock_raven'
$prop = $boot.PSObject.Properties['patch-texpacks']
if ($null -eq $prop) {
    $boot | Add-Member -NotePropertyName 'patch-texpacks' -NotePropertyValue @($patchEntry)
}
else {
    $current = @($boot.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
    if ($current -notcontains $patchEntry) {
        $boot.'patch-texpacks' = @($current + $patchEntry)
    }
}

$json = $boot | ConvertTo-Json -Depth 20
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($bootPath, $json + [Environment]::NewLine, $utf8NoBom)

# Confirm the patch entry survived serialization.
$bootCheck = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
if (@($bootCheck.'patch-texpacks') -notcontains $patchEntry) {
    throw 'Patch texpack entry was not present after writing boot-options.json.'
}

$reportDir = Join-Path $repo 'archive\field-logs'
$report = Join-Path $reportDir 'completionist-v102-dock-raven-proof.txt'
New-Item -ItemType Directory -Force $reportDir | Out-Null

$lines = @(
    '=== Completionist Map v0.10.2 DockPoint Raven texture proof ==='
    "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    "Branch: $branch"
    "GameRoot: $GameRoot"
    ''
    '=== stock DockPoint textures ==='
    "Diffuse:  $([IO.Path]::GetFileName($diffuseOriginal))"
    "Diffuse metadata: $($diffMeta.Width)x$($diffMeta.Height), mips=$($diffMeta.Mips), format=$($diffMeta.Format), FourCC=$($diffMeta.FourCC), DXGI=$($diffMeta.Dxgi)"
    "Emissive: $([IO.Path]::GetFileName($emissiveOriginal))"
    "Emissive metadata: $($emisMeta.Width)x$($emisMeta.Height), mips=$($emisMeta.Mips), format=$($emisMeta.Format), FourCC=$($emisMeta.FourCC), DXGI=$($emisMeta.Dxgi)"
    ''
    '=== generated Raven replacements ==='
    "$diffTargetName SHA256=$((Get-FileHash -LiteralPath $diffTarget -Algorithm SHA256).Hash)"
    "$emisTargetName SHA256=$((Get-FileHash -LiteralPath $emisTarget -Algorithm SHA256).Hash)"
    ''
    '=== patch texpack ==='
    "Installed: $installedPack"
    "Texpack bytes: $((Get-Item -LiteralPath $installedPack).Length)"
    "Texpack SHA256: $((Get-FileHash -LiteralPath $installedPack -Algorithm SHA256).Hash)"
    "TOC bytes: $((Get-Item -LiteralPath $installedToc).Length)"
    "Patch entry: $patchEntry"
    "boot-options backup: $bootBackup"
    ''
    '=== toolchain ==='
    "GOWTool: $gowTool"
    "GOWTool exit: $packExit"
    "texconv: $texconv"
    "texconv SHA256: $actualTexconvHash"
    ''
    '=== expected runtime result ==='
    'All UI objects using the stock DockPoint map-marker diffuse/emissive pair will temporarily render with the Raven artwork.'
    'This intentionally includes normal dock markers and Completionist synthetic DockPoint proxies.'
    'The native Kratos/Omega player textures are not replaced by this patch.'
    'This is a texture-pack loading proof only, not the final per-category icon architecture.'
)
$lines | Set-Content -LiteralPath $report -Encoding UTF8

Write-Host ''
Write-Host 'v0.10.2 DockPoint Raven texture proof installed.'
Write-Host "Patch: $installedPack"
Write-Host "boot-options entry: $patchEntry"
Write-Host 'Expected: DockPoint map icons should render as the Completionist Raven artwork.'
Write-Host 'Kratos/Omega textures were not touched.'
Write-Host "Saved report: $report"

$relativeReport = 'archive/field-logs/completionist-v102-dock-raven-proof.txt'
& git add -- $relativeReport
if ($LASTEXITCODE -ne 0) { throw 'git add failed for the DockPoint Raven proof report.' }
& git diff --cached --quiet -- $relativeReport
if ($LASTEXITCODE -ne 0) {
    & git commit -m 'Archive v0.10.2 DockPoint Raven texture proof' -- $relativeReport
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed for the DockPoint Raven proof report.' }
    & git push $Remote $branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed. The report commit exists locally on '$branch'." }
    Write-Host "Pushed proof report to $Remote/$branch"
}
else {
    Write-Host 'Proof report is unchanged. Nothing to commit.'
}
