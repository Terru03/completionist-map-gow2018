param(
    [string]$GameRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$runtimeTest = Join-Path $PSScriptRoot 'all-ravens-runtime-test.ps1'

function Get-CurrentBranch {
    $branch = (& git -C $repo branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) {
        throw 'Could not determine the current Git branch.'
    }
    return $branch
}

function Resolve-GodOfWarRoot {
    param([string]$RequestedRoot)

    if (-not [string]::IsNullOrWhiteSpace($RequestedRoot)) {
        $resolved = [System.IO.Path]::GetFullPath($RequestedRoot)
        if (-not (Test-Path -LiteralPath $resolved -PathType Container)) {
            throw "God of War root does not exist: $resolved"
        }
        return $resolved
    }

    $candidates = New-Object System.Collections.Generic.List[string]

    foreach ($root in @(
        'G:\SteamLibrary\steamapps\common\GodOfWar',
        'C:\Program Files (x86)\Steam\steamapps\common\GodOfWar',
        'C:\Program Files\Steam\steamapps\common\GodOfWar'
    )) {
        $candidates.Add($root)
    }

    try {
        $steamPath = (Get-ItemProperty -LiteralPath 'HKCU:\Software\Valve\Steam' -ErrorAction Stop).SteamPath
        if (-not [string]::IsNullOrWhiteSpace([string]$steamPath)) {
            $steamPath = ([string]$steamPath).Replace('/', '\')
            $candidates.Add((Join-Path $steamPath 'steamapps\common\GodOfWar'))

            $vdf = Join-Path $steamPath 'steamapps\libraryfolders.vdf'
            if (Test-Path -LiteralPath $vdf -PathType Leaf) {
                foreach ($line in Get-Content -LiteralPath $vdf) {
                    if ($line -match '^\s*"path"\s+"(.+)"\s*$') {
                        $library = $Matches[1].Replace('\\', '\')
                        $candidates.Add((Join-Path $library 'steamapps\common\GodOfWar'))
                    }
                }
            }
        }
    }
    catch {
        # Registry discovery is optional; fixed/common locations are still checked below.
    }

    foreach ($driveLetter in [char[]](67..90)) {
        $drive = "$driveLetter`:"
        $candidates.Add("$drive\SteamLibrary\steamapps\common\GodOfWar")
        $candidates.Add("$drive\Steam\steamapps\common\GodOfWar")
    }

    $matches = @(
        $candidates |
            Select-Object -Unique |
            Where-Object {
                Test-Path -LiteralPath $_ -PathType Container -and
                (Test-Path -LiteralPath (Join-Path $_ 'GoW.exe') -PathType Leaf -or
                 Test-Path -LiteralPath (Join-Path $_ 'GodOfWar.exe') -PathType Leaf -or
                 Test-Path -LiteralPath (Join-Path $_ 'exec') -PathType Container)
            }
    )

    if ($matches.Count -eq 0) {
        throw 'Could not auto-detect the God of War installation. Re-run this script with -GameRoot <path-to-GodOfWar>.'
    }
    if ($matches.Count -gt 1) {
        throw "Multiple God of War installations were found. Re-run with -GameRoot and choose one: $($matches -join '; ')"
    }
    return [System.IO.Path]::GetFullPath($matches[0])
}

if (-not (Test-Path -LiteralPath $runtimeTest -PathType Leaf)) {
    throw "Missing runtime transaction script: $runtimeTest"
}

$branch = Get-CurrentBranch
if ($branch -ne $expectedBranch) {
    throw "Expected branch '$expectedBranch', got '$branch'."
}

$resolvedGameRoot = Resolve-GodOfWarRoot -RequestedRoot $GameRoot

Write-Host 'COMPLETIONIST_MAP_ALL_RAVENS_INSTALL'
Write-Host "  branch: $branch"
Write-Host "  game root: $resolvedGameRoot"
Write-Host '  catalogue markers: 53'
Write-Host '  unknown Raven state: visible'
Write-Host '  live native ravenKilled events: enabled'
Write-Host '  save/progression writes by installer: none'
Write-Host '  transaction: guarded five-file install with pre-write backups'
Write-Host ''

& $runtimeTest -Mode Install -GameRoot $resolvedGameRoot -ConfirmRuntimeTest
if ($LASTEXITCODE -ne 0) {
    throw "All-Ravens runtime installer failed with exit code $LASTEXITCODE."
}

Write-Host ''
Write-Host 'COMPLETIONIST_MAP_ALL_RAVENS_READY'
Write-Host '  The 53-Raven catalogue build is installed.'
Write-Host '  A Raven killed during this runtime is hidden by its exact native ravenKilled event.'
Write-Host '  Existing kills from an old save are not yet reconstructed until the persisted-kill bootstrap is completed.'
Write-Host '  Fresh/unknown Raven state remains visible by design.'
