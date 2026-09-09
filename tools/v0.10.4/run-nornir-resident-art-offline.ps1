param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedBranch = 'codex/v104-raven-production'
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not determine current Git branch.' }
if ($branch -ne $expectedBranch) { throw "Expected branch '$expectedBranch', got '$branch'." }
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before building Nornir resident art.' }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
$verify = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$builder = Join-Path $PSScriptRoot 'build-nornir-resident-art-offline.py'
foreach ($required in @($verify, $builder)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required tool: $required" }
}

Write-Host 'Re-verifying frozen Raven production state before building real Nornir art payloads...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed.' }

$topologyReport = Join-Path $repo 'build\v0.10.4-nornir-resource-topology\nornir-resource-topology.json'
if (-not (Test-Path -LiteralPath $topologyReport -PathType Leaf)) { throw "Nornir resource topology report missing: $topologyReport" }
$topology = Get-Content -LiteralPath $topologyReport -Raw | ConvertFrom-Json
if ($topology.result -ne 'NORNIR_RESOURCE_TOPOLOGY_VERIFIED' -or -not $topology.ready_for_nornir_resource_builder) {
    throw 'Nornir resource topology gate is not in a builder-ready state.'
}

$art = Join-Path $repo 'assets\icons\concepts\nornir_chest_concept_master.png'
if (-not (Test-Path -LiteralPath $art -PathType Leaf)) { throw "Nornir concept art missing: $art" }

$gowTool = Join-Path $env:LOCALAPPDATA 'CompletionistMap\tools\GOWTool-v0.1.3-alpha\GOWTool.exe'
$gowToolSha = 'C1B0F3C7FB9DD2B26AE7EF4AC377308761FD3C7AFB21DAC7E4BEE20160A0008B'
if (-not (Test-Path -LiteralPath $gowTool -PathType Leaf)) { throw "GOWTool missing: $gowTool" }
if ((Get-FileHash -LiteralPath $gowTool -Algorithm SHA256).Hash -ne $gowToolSha) { throw 'GOWTool SHA256 does not match the pinned v0.1.3-alpha binary.' }

$dxRoot = Join-Path $env:LOCALAPPDATA 'CompletionistMap\tools\DirectXTex-may2026'
$texconv = Join-Path $dxRoot 'texconv.exe'
$texconvUrl = 'https://github.com/microsoft/DirectXTex/releases/download/may2026/texconv.exe'
$texconvSha = 'DCFDEC10244E02CF5037FBA089C55FB7E1326B1C8181742D77D15FA5CB5EEF06'
New-Item -ItemType Directory -Force -Path $dxRoot | Out-Null
if (-not (Test-Path -LiteralPath $texconv -PathType Leaf)) {
    Write-Host 'Downloading pinned DirectXTex texconv (May 2026)...'
    Invoke-WebRequest -Uri $texconvUrl -OutFile $texconv -UseBasicParsing
}
if ((Get-FileHash -LiteralPath $texconv -Algorithm SHA256).Hash -ne $texconvSha) { throw 'texconv SHA256 does not match the pinned May 2026 binary.' }

$work = Join-Path $repo 'build\v0.10.4-nornir-resident-art\offline'
$packRoot = Join-Path $work 'texpack'
$inputDir = Join-Path $packRoot 'completionist_v104_nornir_chest_map'
$diffTemp = Join-Path $packRoot 'diffuse'
$emisTemp = Join-Path $packRoot 'emissive'
$residentDir = Join-Path $work 'resident'
$report = Join-Path $work 'nornir-resident-art.json'
Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $inputDir, $diffTemp, $emisTemp, $residentDir | Out-Null

Write-Host 'Converting verified Nornir concept art to the exact 148x148 map-icon texture contract...'
$diffOutput = @(& $texconv -nologo -y -w 148 -h 148 -m 8 -f BC7_UNORM_SRGB -o $diffTemp $art 2>&1)
if ($LASTEXITCODE -ne 0) { $diffOutput | ForEach-Object { Write-Host $_ }; throw 'texconv failed for Nornir diffuse.' }
$emisOutput = @(& $texconv -nologo -y -w 148 -h 148 -m 8 -f BC1_UNORM -o $emisTemp $art 2>&1)
if ($LASTEXITCODE -ne 0) { $emisOutput | ForEach-Object { Write-Host $_ }; throw 'texconv failed for Nornir emissive.' }

$generatedDiffuse = Join-Path $diffTemp 'nornir_chest_concept_master.dds'
$generatedEmissive = Join-Path $emisTemp 'nornir_chest_concept_master.dds'
$diffName = 'TX_completionist_nornir_chest_map_diffuse_0A43AEB29D6F80DA.dds'
$emisName = 'TX_completionist_nornir_chest_map_emissive_58012A499511A0BB.dds'
$diffDds = Join-Path $inputDir $diffName
$emisDds = Join-Path $inputDir $emisName
foreach ($generated in @($generatedDiffuse, $generatedEmissive)) {
    if (-not (Test-Path -LiteralPath $generated -PathType Leaf)) { throw "texconv output missing: $generated" }
}
Move-Item -LiteralPath $generatedDiffuse -Destination $diffDds -Force
Move-Item -LiteralPath $generatedEmissive -Destination $emisDds -Force

Write-Host 'Building the Nornir texpack with pinned GOWTool...'
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

$texpack = Join-Path $packRoot 'completionist_v104_nornir_chest_map.texpack'
$texpackToc = Join-Path $packRoot 'completionist_v104_nornir_chest_map.texpack.toc'
foreach ($required in @($texpack, $texpackToc)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Expected texpack output missing: $required" }
}

& $python.Source -m py_compile $builder
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed for Nornir resident-art builder.' }

$ravenWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
Write-Host 'Reconstructing the real Nornir resident payloads with the runtime-proven partial-linearization transform...'
& $python.Source $builder --raven-wad $ravenWad --nornir-texpack $texpack --output-dir $residentDir --report $report
if ($LASTEXITCODE -ne 0) { throw 'Offline Nornir resident-art build failed.' }
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) { throw 'Nornir resident-art report was not produced.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($proof.result -ne 'OFFLINE_NORNIR_RESIDENT_ART_BUILT' -or -not $proof.ready_for_nornir_wad_clone) {
    throw 'Nornir resident-art report did not pass the WAD-clone gate.'
}
if ($proof.game_files_written -or $proof.runtime_install_performed -or $proof.save_state_written -or $proof.progression_state_written -or $proof.marker_state_written) {
    throw 'Nornir resident-art safety contract failed.'
}

Write-Host 'Re-verifying Raven production state after the offline art build...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Raven production state changed during offline Nornir art build.' }

Write-Host 'NORNIR_RESIDENT_ART_OFFLINE_GATE_PASSED'
foreach ($row in $proof.rows) {
    Write-Host "$($row.label): $($row.resource_name)"
    Write-Host "  resident bytes: $($row.resident_bytes)"
    Write-Host "  sha256:         $($row.resident_sha256)"
}
Write-Host "texpack SHA256: $($proof.nornir_texpack_sha256)"
Write-Host 'runtime-proven partial-linearization reused: true'
Write-Host 'Raven production files changed: false'
Write-Host 'game files written: false'
Write-Host 'runtime install performed: false'
Write-Host "report: $report"
Write-Host 'Do not install these payloads manually. The next gate injects them into a fully reparsed Nornir map/HUD WAD clone and adds the planned GOPool rows offline.'
