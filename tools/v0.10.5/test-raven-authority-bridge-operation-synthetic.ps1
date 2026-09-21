$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$library = Join-Path $PSScriptRoot 'raven-authority-bridge-operation.ps1'
if (-not (Test-Path -LiteralPath $library -PathType Leaf)) {
    throw "Missing bridge operation library: $library"
}
. $library

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Write-Bytes([string]$Path, [byte[]]$Bytes) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    [IO.File]::WriteAllBytes($Path, $Bytes)
}

function Write-OwnedManifest([string]$Path, [string]$Sha) {
    $value = [ordered]@{
        schema = 3
        owner = 'completionist-map-raven-authority-bridge'
        installed_utc = '2026-09-21T00:00:00Z'
        target_relative = 'dxgi.dll'
        proxy_contract = 'system32-dxgi-v1'
        installed_sha256 = $Sha
        supported_exe_sha256 = ('0' * 64)
        version_dll_sha256 = ('1' * 64)
        build_git_commit = 'synthetic'
        backup_relative = $null
        backup_manifest_relative = $null
        save_writes = $false
        progression_writes = $false
    }
    Write-RavenBridgeJsonAtomic -Value $value -Path $Path
}

function Reset-CaseRoot([string]$Root) {
    Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
}

$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/')
$root = Join-Path $tempBase (
    'completionist-raven-bridge-operation-' + [Guid]::NewGuid().ToString('N'))

try {
    $caseRoot = Join-Path $root 'case'
    $target = Join-Path $caseRoot 'dxgi.dll'
    $manifest = Join-Path $caseRoot 'mods\completionist-map\native\raven-native-bridge-manifest.json'
    $backupRel = 'mods\completionist-map\native\backups\previous.dll'
    $backupManifestRel = 'mods\completionist-map\native\backups\previous.json'
    $backup = Join-Path $caseRoot $backupRel
    $backupManifest = Join-Path $caseRoot $backupManifestRel

    $oldBytes = [byte[]](1,3,5,7,9,11)
    $newBytes = [byte[]](2,4,6,8,10,12)
    $unknownBytes = [byte[]](99,98,97)
    $oldTemp = Join-Path $root 'old.bin'
    $newTemp = Join-Path $root 'new.bin'
    Write-Bytes $oldTemp $oldBytes
    Write-Bytes $newTemp $newBytes
    $oldSha = Get-RavenBridgeHash $oldTemp
    $newSha = Get-RavenBridgeHash $newTemp

    # Case 1: rollback/install interruption after previous DLL was restored but
    # before the previous manifest replaced the current manifest.
    Reset-CaseRoot $caseRoot
    Write-Bytes $target $oldBytes
    Write-OwnedManifest $manifest $newSha
    Write-Bytes $backup $oldBytes
    Write-OwnedManifest $backupManifest $oldSha
    $op1 = New-RavenBridgeOperation -GameRoot $caseRoot -Operation 'rollback' -OperationSha256 $newSha -RestoreExists $true -RestoreSha256 $oldSha -RestoreDllRelative $backupRel -RestoreManifestRelative $backupManifestRel
    $result1 = Complete-RavenBridgeInterruptedOperation -GameRoot $caseRoot
    Assert-True $result1.Recovered 'Mixed pair recovery did not run.'
    Assert-True ((Get-RavenBridgeHash $target) -eq $oldSha) 'Mixed pair recovery changed previous DLL.'
    $m1 = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    Assert-True (([string]$m1.installed_sha256).ToLowerInvariant() -eq $oldSha) 'Mixed pair recovery did not restore previous manifest.'
    Assert-True (-not (Test-Path -LiteralPath $op1.Path)) 'Mixed pair journal remained.'

    # Case 2: interruption after current DLL removal, before previous DLL move.
    Reset-CaseRoot $caseRoot
    Write-OwnedManifest $manifest $newSha
    Write-Bytes $backup $oldBytes
    Write-OwnedManifest $backupManifest $oldSha
    $op2 = New-RavenBridgeOperation -GameRoot $caseRoot -Operation 'rollback' -OperationSha256 $newSha -RestoreExists $true -RestoreSha256 $oldSha -RestoreDllRelative $backupRel -RestoreManifestRelative $backupManifestRel
    $result2 = Complete-RavenBridgeInterruptedOperation -GameRoot $caseRoot
    Assert-True $result2.Recovered 'Missing-target recovery did not run.'
    Assert-True ((Get-RavenBridgeHash $target) -eq $oldSha) 'Missing-target recovery did not restore previous DLL.'
    $m2 = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    Assert-True (([string]$m2.installed_sha256).ToLowerInvariant() -eq $oldSha) 'Missing-target recovery did not restore manifest.'

    # Case 3: clean install/rollback interruption with desired state absent:
    # target already removed but current manifest remains.
    Reset-CaseRoot $caseRoot
    Write-OwnedManifest $manifest $newSha
    $op3 = New-RavenBridgeOperation -GameRoot $caseRoot -Operation 'rollback' -OperationSha256 $newSha -RestoreExists $false -RestoreSha256 '' -RestoreDllRelative '' -RestoreManifestRelative ''
    $result3 = Complete-RavenBridgeInterruptedOperation -GameRoot $caseRoot
    Assert-True $result3.Recovered 'Absent-state recovery did not run.'
    Assert-True (-not (Test-Path -LiteralPath $target)) 'Absent-state recovery left target.'
    Assert-True (-not (Test-Path -LiteralPath $manifest)) 'Absent-state recovery left manifest.'
    Assert-True (-not (Test-Path -LiteralPath $op3.Path)) 'Absent-state journal remained.'

    # Case 4: unknown DLL must remain untouched and journal must remain for
    # human review instead of silently overwriting foreign state.
    Reset-CaseRoot $caseRoot
    Write-Bytes $target $unknownBytes
    Write-OwnedManifest $manifest $newSha
    Write-Bytes $backup $oldBytes
    Write-OwnedManifest $backupManifest $oldSha
    $op4 = New-RavenBridgeOperation -GameRoot $caseRoot -Operation 'install' -OperationSha256 $newSha -RestoreExists $true -RestoreSha256 $oldSha -RestoreDllRelative $backupRel -RestoreManifestRelative $backupManifestRel
    $unknownSha = Get-RavenBridgeHash $target
    $refused = $false
    try {
        [void](Complete-RavenBridgeInterruptedOperation -GameRoot $caseRoot)
    }
    catch {
        $refused = $_.Exception.Message -like '*unknown dxgi.dll SHA*'
    }
    Assert-True $refused 'Unknown DLL was not refused during journal recovery.'
    Assert-True ((Get-RavenBridgeHash $target) -eq $unknownSha) 'Unknown DLL changed during refused recovery.'
    Assert-True (Test-Path -LiteralPath $op4.Path -PathType Leaf) 'Refused recovery removed its journal.'

    Write-Host 'RAVEN_BRIDGE_OPERATION_SYNTHETIC_PASSED mixed_pair=true missing_target=true absent_pair=true unknown_refused=true'
}
finally {
    $resolved = [IO.Path]::GetFullPath($root)
    if ($resolved.StartsWith(
        $tempBase + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
    }
}
