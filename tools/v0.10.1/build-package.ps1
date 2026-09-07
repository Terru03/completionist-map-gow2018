param(
    [string]$OutputName = 'Completionist-Map-v0.10.1-LOCAL-ICONS.zip'
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path (Split-Path $scriptDir -Parent) -Parent
$installer = Join-Path $scriptDir 'install.ps1'
$uninstaller = Join-Path $scriptDir 'uninstall.ps1'
$readme = Join-Path $scriptDir 'README.txt'
$assetSource = Join-Path $repoRoot 'assets\icons\concepts'
$distRoot = Join-Path $repoRoot 'dist'
$stage = Join-Path $distRoot 'v0.10.1-package'
$zipPath = Join-Path $distRoot $OutputName

foreach ($required in @($installer, $uninstaller, $readme, $assetSource)) {
    if (-not (Test-Path $required)) {
        throw "Missing package input: $required"
    }
}

$installerText = [IO.File]::ReadAllText($installer)
if ($installerText.Contains('Get-CompletionistGitHubBinary') -or
    $installerText.Contains('gh auth token') -or
    $installerText.Contains('$IconRepo =')) {
    throw 'install.ps1 still contains the old private GitHub icon-fetch path. Run prepare-local-retry.ps1 first.'
}
if (-not $installerText.Contains('$IconSourceDir')) {
    throw 'install.ps1 does not contain v0.10.1 local icon source resolution.'
}

$masters = @(Get-ChildItem $assetSource -File -Filter '*_concept_master.png')
if ($masters.Count -ne 10) {
    throw "Expected exactly 10 concept PNG masters, found $($masters.Count) in $assetSource"
}

Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$stageAssets = Join-Path $stage 'assets\icons\concepts'
New-Item -ItemType Directory -Force -Path $stageAssets | Out-Null

Copy-Item $installer (Join-Path $stage 'install.ps1') -Force
Copy-Item $uninstaller (Join-Path $stage 'uninstall.ps1') -Force
Copy-Item $readme (Join-Path $stage 'README.txt') -Force
Copy-Item $masters.FullName $stageAssets -Force

Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zipPath -CompressionLevel Optimal

$zip = Get-Item $zipPath
Write-Host ''
Write-Host 'Built Completionist Map v0.10.1 local-icons test package.'
Write-Host "ZIP: $($zip.FullName)"
Write-Host ("Size: {0:N2} MiB" -f ($zip.Length / 1MB))
Write-Host 'Included concept masters: 10'
Write-Host 'Installer network dependency for icon assets: none'
