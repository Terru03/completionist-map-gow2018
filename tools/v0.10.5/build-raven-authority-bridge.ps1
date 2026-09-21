param(
    [string]$Configuration = 'Release',
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
$source = Join-Path $repo 'native\raven-authority-bridge'
$build = Join-Path $repo 'build\raven-authority-bridge'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) { throw 'Visual Studio Build Tools not found.' }
$vs = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath).Trim()
if ([string]::IsNullOrWhiteSpace($vs)) { throw 'MSVC x64 build tools not found.' }
if ($Clean -and (Test-Path -LiteralPath $build -PathType Container)) {
    $resolvedRepo = [IO.Path]::GetFullPath($repo)
    $resolvedBuild = [IO.Path]::GetFullPath($build)
    if (-not $resolvedBuild.StartsWith($resolvedRepo + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to clean build path outside repository.'
    }
    Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
}

& cmake -S $source -B $build -G 'Visual Studio 17 2022' -A x64 -DBUILD_TESTING=ON
if ($LASTEXITCODE -ne 0) { throw 'CMake configure failed.' }
& cmake --build $build --config $Configuration --parallel
if ($LASTEXITCODE -ne 0) { throw 'Bridge build failed.' }
& ctest --test-dir $build -C $Configuration --output-on-failure
if ($LASTEXITCODE -ne 0) { throw 'Bridge tests failed.' }

$dll = Join-Path $build "$Configuration\dxgi.dll"
if (-not (Test-Path -LiteralPath $dll -PathType Leaf)) { throw "Built DLL missing: $dll" }
$hash = (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "RAVEN_NATIVE_BRIDGE_BUILD_OK dll=$dll sha256=$hash"
