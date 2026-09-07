param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'

$repo = (& git rev-parse --show-toplevel).Trim()
if (-not $repo) { throw 'Run this script from inside the Completionist Map Git repository.' }
$branch = (& git branch --show-current).Trim()
if (-not $branch) { throw 'Detached HEAD is not supported.' }
if (-not (Test-Path -LiteralPath $GameRoot)) { throw "God of War root not found: $GameRoot" }
if (Get-Process -Name 'GoW' -ErrorAction SilentlyContinue) {
    throw 'God of War is running. Close the game before installing the HUD texture proof.'
}

$workRoot = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.2'
$ruiDds = Join-Path $workRoot 'r_ui-dds'
$l3Original = Join-Path $ruiDds 'TX_macrol3_8E35C12706322C80.dds'
$r3Original = Join-Path $ruiDds 'TX_macror3_1DDD5B5FE1AB2D29.dds'
$ravenPng = Join-Path $repo 'assets\icons\concepts\raven_concept_master.png'
$gowTool = Join-Path $env:LOCALAPPDATA 'CompletionistMap\tools\GOWTool-v0.1.3-alpha\GOWTool.exe'

foreach ($required in @($l3Original, $r3Original, $ravenPng, $gowTool)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required file not found: $required"
    }
}

function Get-DdsMetadata {
    param([Parameter(Mandatory=$true)][string]$Path)

    $fs = [IO.File]::OpenRead($Path)
    try {
        $br = New-Object IO.BinaryReader($fs)
        if ($br.ReadUInt32() -ne 0x20534444) { throw "Not a DDS file: $Path" }
        $headerSize = $br.ReadUInt32()
        if ($headerSize -ne 124) { throw "Unexpected DDS header size $headerSize in $Path" }
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

$l3Meta = Get-DdsMetadata -Path $l3Original
$r3Meta = Get-DdsMetadata -Path $r3Original
Write-Host "L3 texture: $($l3Meta.Width)x$($l3Meta.Height), mips=$($l3Meta.Mips), format=$($l3Meta.Format)"
Write-Host "R3 texture: $($r3Meta.Width)x$($r3Meta.Height), mips=$($r3Meta.Mips), format=$($r3Meta.Format)"

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

$buildRoot = Join-Path $workRoot 'hud-r3l3-raven-proof'
$l3Temp = Join-Path $buildRoot 'l3'
$r3Temp = Join-Path $buildRoot 'r3'
$packBase = '0Completionist_v102_hud_r3l3_raven'
$inputDir = Join-Path $buildRoot $packBase
Remove-Item -LiteralPath $buildRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $l3Temp, $r3Temp, $inputDir | Out-Null

function Convert-RavenDds {
    param(
        [Parameter(Mandatory=$true)]$Meta,
        [Parameter(Mandatory=$true)][string]$OutDir,
        [Parameter(Mandatory=$true)][string]$TargetName
    )

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

$l3TargetName = 'TX_completionist_raven_hud_l3_8E35C12706322C80.dds'
$r3TargetName = 'TX_completionist_raven_hud_r3_1DDD5B5FE1AB2D29.dds'
$l3Target = Convert-RavenDds -Meta $l3Meta -OutDir $l3Temp -TargetName $l3TargetName
$r3Target = Convert-RavenDds -Meta $r3Meta -OutDir $r3Temp -TargetName $r3TargetName

$l3GeneratedMeta = Get-DdsMetadata -Path $l3Target
$r3GeneratedMeta = Get-DdsMetadata -Path $r3Target
foreach ($check in @(
    @{ Label='L3'; Expected=$l3Meta; Actual=$l3GeneratedMeta },
    @{ Label='R3'; Expected=$r3Meta; Actual=$r3GeneratedMeta }
)) {
    if ($check.Expected.Width -ne $check.Actual.Width -or
        $check.Expected.Height -ne $check.Actual.Height -or
        $check.Expected.Mips -ne $check.Actual.Mips -or
        $check.Expected.Format -ne $check.Actual.Format) {
        throw "Generated $($check.Label) DDS metadata does not match the stock texture."
    }
}

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
    throw "GOWTool HUD texpack import failed with exit code $packExit"
}

$builtPack = Join-Path $buildRoot ($packBase + '.texpack')
$builtToc = Join-Path $buildRoot ($packBase + '.texpack.toc')
if (-not (Test-Path -LiteralPath $builtPack)) { throw "Built texpack not found: $builtPack" }
if (-not (Test-Path -LiteralPath $builtToc)) { throw "Built texpack TOC not found: $builtToc" }

$wadDir = Join-Path $GameRoot 'exec\wad\pc_le'
$installedPack = Join-Path $wadDir ($packBase + '.texpack')
$installedToc = Join-Path $wadDir ($packBase + '.texpack.toc')
Copy-Item -LiteralPath $builtPack -Destination $installedPack -Force
Copy-Item -LiteralPath $builtToc -Destination $installedToc -Force

$bootPath = Join-Path $GameRoot 'exec\boot-options.json'
if (-not (Test-Path -LiteralPath $bootPath)) { throw "boot-options.json not found: $bootPath" }
$backup = "$bootPath.completionist-v102-before-hud-r3l3-proof.bak"
if (-not (Test-Path -LiteralPath $backup)) {
    Copy-Item -LiteralPath $bootPath -Destination $backup
}

$boot = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
$prop = $boot.PSObject.Properties['patch-texpacks']
if ($null -eq $prop) {
    $boot | Add-Member -NotePropertyName 'patch-texpacks' -NotePropertyValue @($packBase)
}
else {
    $current = @(
        @($boot.'patch-texpacks') | Where-Object { $_ -ne $null -and [string]$_ -ne '' }
    )
    if ($current -notcontains $packBase) {
        $nextEntries = @($current)
        $nextEntries += [string]$packBase
        $boot.'patch-texpacks' = [string[]]$nextEntries
    }
}

$json = $boot | ConvertTo-Json -Depth 20
$utf8NoBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($bootPath, $json + [Environment]::NewLine, $utf8NoBom)

$checkBoot = Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
$entries = @($checkBoot.'patch-texpacks')
if ($entries -notcontains $packBase) {
    throw 'HUD proof entry was not present after writing boot-options.json.'
}

$reportDir = Join-Path $repo 'archive\field-logs'
$report = Join-Path $reportDir 'completionist-v102-hud-r3l3-raven-proof.txt'
New-Item -ItemType Directory -Force $reportDir | Out-Null

$lines = @(
    '=== Completionist Map v0.10.2 HUD R3_L3 Raven texture proof ==='
    "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    "Branch: $branch"
    "GameRoot: $GameRoot"
    ''
    '=== target HUD carrier ==='
    'GameObject: R3_L3'
    'Purpose: temporary HUD-native carrier already used by Completionist arbitrary-XYZ compass tracking'
    ''
    '=== stock textures targeted ==='
    "L3: $([IO.Path]::GetFileName($l3Original))"
    "L3 metadata: $($l3Meta.Width)x$($l3Meta.Height), mips=$($l3Meta.Mips), format=$($l3Meta.Format), FourCC=$($l3Meta.FourCC), DXGI=$($l3Meta.Dxgi)"
    "R3: $([IO.Path]::GetFileName($r3Original))"
    "R3 metadata: $($r3Meta.Width)x$($r3Meta.Height), mips=$($r3Meta.Mips), format=$($r3Meta.Format), FourCC=$($r3Meta.FourCC), DXGI=$($r3Meta.Dxgi)"
    ''
    '=== generated replacements ==='
    "$l3TargetName SHA256=$((Get-FileHash -LiteralPath $l3Target -Algorithm SHA256).Hash)"
    "$r3TargetName SHA256=$((Get-FileHash -LiteralPath $r3Target -Algorithm SHA256).Hash)"
    ''
    '=== installed texpack ==='
    "Texpack: $installedPack"
    "TOC: $installedToc"
    "Texpack SHA256: $((Get-FileHash -LiteralPath $installedPack -Algorithm SHA256).Hash)"
    "boot-options entry: $packBase"
    "boot-options entries: $($entries -join ', ')"
    "boot-options backup: $backup"
    ''
    '=== expected runtime result ==='
    'The borrowed R3_L3 HUD proof visual should visibly change from its stock L3/R3 artwork to Raven artwork.'
    'Because both L3 and R3 textures are replaced for this diagnostic, the proof may show two Raven components or an imperfect composite.'
    'That is acceptable for this diagnostic. The next step is single-slot/material isolation and final sizing/centering.'
    'The working map DockPoint Raven proof remains loaded if its boot entry was already present.'
    'No Kratos/Omega texture hashes are contained in this HUD proof pack.'
    ''
    '=== warning ==='
    'This is diagnostic only. It temporarily replaces the stock L3/R3 macro textures anywhere the game uses those same texture hashes.'
)
$lines | Set-Content -LiteralPath $report -Encoding UTF8

Write-Host ''
Write-Host 'Installed v0.10.2 HUD R3_L3 Raven proof.'
Write-Host "Texpack: $installedPack"
Write-Host "boot-options entries: $($entries -join ', ')"
Write-Host 'Expected: the moving Completionist HUD proof visual should now use Raven artwork.'
Write-Host 'The result may contain two Raven components because R3_L3 has two material slots.'
Write-Host 'Kratos/Omega textures were not touched.'
Write-Host "Saved report: $report"

$relativeReport = 'archive/field-logs/completionist-v102-hud-r3l3-raven-proof.txt'
& git add -- $relativeReport
if ($LASTEXITCODE -ne 0) { throw 'git add failed for the HUD proof report.' }
& git diff --cached --quiet -- $relativeReport
if ($LASTEXITCODE -eq 0) {
    Write-Host 'HUD proof report is unchanged. Nothing to commit.'
    exit 0
}
& git commit -m 'Archive v0.10.2 HUD R3 L3 Raven proof' -- $relativeReport
if ($LASTEXITCODE -ne 0) { throw 'git commit failed for the HUD proof report.' }
& git push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw "git push failed. The HUD proof report commit exists locally on '$branch'." }
Write-Host "Pushed HUD proof report to $Remote/$branch"
