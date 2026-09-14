param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$source = Join-Path $PSScriptRoot 'object-token-reader.cpp'
$vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Source missing: $source" }
if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) { throw "vswhere missing: $vswhere" }
$installation = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath).Trim()
if ([string]::IsNullOrWhiteSpace($installation)) { throw 'Visual C++ build tools not found.' }
$vcvars = Join-Path $installation 'VC\Auxiliary\Build\vcvars64.bat'
if (-not (Test-Path -LiteralPath $vcvars -PathType Leaf)) { throw "vcvars64.bat missing: $vcvars" }

$resolvedOutput = [IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $resolvedOutput
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$objectPath = [IO.Path]::ChangeExtension($resolvedOutput, '.obj')
$compile = '"{0}" >nul && cl.exe /nologo /std:c++17 /O2 /GS /guard:cf /W4 /WX /LD /EHsc- /GR- "{1}" /Fo"{2}" /link /OUT:"{3}" /NOIMPLIB /NOEXP' -f $vcvars, $source, $objectPath, $resolvedOutput
& cmd.exe /d /s /c $compile
if ($LASTEXITCODE -ne 0) { throw "Native token reader build failed with exit $LASTEXITCODE." }
if (-not (Test-Path -LiteralPath $resolvedOutput -PathType Leaf)) { throw 'Native token reader output missing.' }

$verify = '"{0}" >nul && dumpbin.exe /nologo /exports "{1}" | findstr.exe /L /C:"luaopen_completionist_object_token" >nul' -f $vcvars, $resolvedOutput
& cmd.exe /d /s /c $verify
if ($LASTEXITCODE -ne 0) { throw 'Native token reader export verification failed.' }

Remove-Item -LiteralPath $objectPath -Force -ErrorAction SilentlyContinue
Write-Host "OBJECT_TOKEN_READER_BUILT output=$resolvedOutput export=luaopen_completionist_object_token"
