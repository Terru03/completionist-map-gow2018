Set-StrictMode -Version Latest

$script:RavenBridgeOwner = 'completionist-map-raven-authority-bridge'
$script:RavenBridgeOperationOwner = 'completionist-map-raven-authority-bridge-operation'
$script:RavenBridgeOperationSchema = 1
$script:RavenBridgeManifestSchema = 3
$script:RavenBridgeTargetRelative = 'dxgi.dll'
$script:RavenBridgeProxyContract = 'system32-dxgi-v1'
$script:RavenBridgeManifestRelative = 'mods\completionist-map\native\raven-native-bridge-manifest.json'
$script:RavenBridgeOperationRelative = 'mods\completionist-map\native\raven-native-bridge-operation.json'

function Get-RavenBridgeHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-RavenBridgeChildPath([string]$Root, [string]$Path) {
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $pathFull = [IO.Path]::GetFullPath($Path)
    if (-not $pathFull.StartsWith(
        $rootFull + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path left game root: $pathFull"
    }
    return $pathFull
}

function Write-RavenBridgeJsonAtomic([object]$Value, [string]$Path) {
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $temp = "$Path.tmp-$([Guid]::NewGuid().ToString('N'))"
    $encoding = New-Object Text.UTF8Encoding($false)
    try {
        $json = $Value | ConvertTo-Json -Depth 12
        [IO.File]::WriteAllText($temp, $json + [Environment]::NewLine, $encoding)
        Move-Item -LiteralPath $temp -Destination $Path -Force
    }
    finally {
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    }
}

function Copy-RavenBridgeFileAtomic(
    [string]$Source,
    [string]$Destination,
    [string]$ExpectedSha
) {
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $temp = "$Destination.tmp-$([Guid]::NewGuid().ToString('N'))"
    try {
        Copy-Item -LiteralPath $Source -Destination $temp -Force
        if ((Get-RavenBridgeHash $temp) -ne $ExpectedSha.ToLowerInvariant()) {
            throw "Temporary bridge file SHA mismatch: $Destination"
        }
        Move-Item -LiteralPath $temp -Destination $Destination -Force
        if ((Get-RavenBridgeHash $Destination) -ne $ExpectedSha.ToLowerInvariant()) {
            throw "Bridge file SHA mismatch after atomic move: $Destination"
        }
    }
    finally {
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    }
}

function Assert-RavenBridgeOwnedManifest(
    [object]$Manifest,
    [string]$ExpectedSha = ''
) {
    if ($Manifest.schema -ne $script:RavenBridgeManifestSchema -or
        $Manifest.owner -ne $script:RavenBridgeOwner -or
        $Manifest.target_relative -ne $script:RavenBridgeTargetRelative -or
        $Manifest.proxy_contract -ne $script:RavenBridgeProxyContract) {
        throw 'Bridge manifest is not recognized schema-3 ownership.'
    }
    $installed = ([string]$Manifest.installed_sha256).ToLowerInvariant()
    if ($installed -notmatch '^[0-9a-f]{64}$') {
        throw 'Bridge manifest installed SHA is invalid.'
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedSha) -and
        $installed -ne $ExpectedSha.ToLowerInvariant()) {
        throw 'Bridge manifest installed SHA differs from expected operation state.'
    }
    return $installed
}

function New-RavenBridgeOperation(
    [string]$GameRoot,
    [ValidateSet('install','rollback')][string]$Operation,
    [string]$OperationSha256,
    [bool]$RestoreExists,
    [string]$RestoreSha256,
    [string]$RestoreDllRelative,
    [string]$RestoreManifestRelative
) {
    $game = [IO.Path]::GetFullPath($GameRoot)
    $operationPath = Assert-RavenBridgeChildPath $game (
        Join-Path $game $script:RavenBridgeOperationRelative)

    if (Test-Path -LiteralPath $operationPath -PathType Leaf) {
        throw "Bridge operation journal already exists: $operationPath"
    }
    if ($OperationSha256.ToLowerInvariant() -notmatch '^[0-9a-f]{64}$') {
        throw 'Bridge operation SHA is invalid.'
    }
    if ($RestoreExists) {
        if ($RestoreSha256.ToLowerInvariant() -notmatch '^[0-9a-f]{64}$' -or
            [string]::IsNullOrWhiteSpace($RestoreDllRelative) -or
            [string]::IsNullOrWhiteSpace($RestoreManifestRelative)) {
            throw 'Bridge restore journal is incomplete.'
        }
    }

    $journal = [ordered]@{
        schema = $script:RavenBridgeOperationSchema
        owner = $script:RavenBridgeOperationOwner
        operation = $Operation
        phase = 'prepared'
        created_utc = (Get-Date).ToUniversalTime().ToString('o')
        target_relative = $script:RavenBridgeTargetRelative
        proxy_contract = $script:RavenBridgeProxyContract
        operation_sha256 = $OperationSha256.ToLowerInvariant()
        restore_exists = $RestoreExists
        restore_sha256 = if ($RestoreExists) { $RestoreSha256.ToLowerInvariant() } else { $null }
        restore_dll_relative = if ($RestoreExists) { $RestoreDllRelative } else { $null }
        restore_manifest_relative = if ($RestoreExists) { $RestoreManifestRelative } else { $null }
        save_writes = $false
        progression_writes = $false
    }
    Write-RavenBridgeJsonAtomic -Value $journal -Path $operationPath
    return [pscustomobject]@{
        Path = $operationPath
        Journal = $journal
    }
}

function Set-RavenBridgeOperationPhase(
    [string]$OperationPath,
    [object]$Journal,
    [string]$Phase
) {
    $Journal.phase = $Phase
    Write-RavenBridgeJsonAtomic -Value $Journal -Path $OperationPath
}

function Get-RavenBridgeOperationPath([string]$GameRoot) {
    $game = [IO.Path]::GetFullPath($GameRoot)
    return Assert-RavenBridgeChildPath $game (
        Join-Path $game $script:RavenBridgeOperationRelative)
}

function Complete-RavenBridgeInterruptedOperation([string]$GameRoot) {
    $game = [IO.Path]::GetFullPath($GameRoot)
    $operationPath = Get-RavenBridgeOperationPath $game
    if (-not (Test-Path -LiteralPath $operationPath -PathType Leaf)) {
        return [pscustomobject]@{ Recovered = $false; Operation = $null; RestoredPrevious = $false }
    }

    $journal = Get-Content -LiteralPath $operationPath -Raw | ConvertFrom-Json
    if ($journal.schema -ne $script:RavenBridgeOperationSchema -or
        $journal.owner -ne $script:RavenBridgeOperationOwner -or
        [string]$journal.operation -notin @('install','rollback') -or
        $journal.target_relative -ne $script:RavenBridgeTargetRelative -or
        $journal.proxy_contract -ne $script:RavenBridgeProxyContract) {
        throw 'Bridge operation journal is not recognized.'
    }

    $operationSha = ([string]$journal.operation_sha256).ToLowerInvariant()
    if ($operationSha -notmatch '^[0-9a-f]{64}$') {
        throw 'Bridge operation journal SHA is invalid.'
    }

    $target = Assert-RavenBridgeChildPath $game (
        Join-Path $game $script:RavenBridgeTargetRelative)
    $manifestPath = Assert-RavenBridgeChildPath $game (
        Join-Path $game $script:RavenBridgeManifestRelative)
    $restoreExists = [bool]$journal.restore_exists
    $restoreSha = if ($restoreExists) {
        ([string]$journal.restore_sha256).ToLowerInvariant()
    } else { $null }

    $targetExists = Test-Path -LiteralPath $target -PathType Leaf
    if ($targetExists) {
        $currentSha = Get-RavenBridgeHash $target
        $allowed = @($operationSha)
        if ($restoreExists) { $allowed += $restoreSha }
        if ($currentSha -notin $allowed) {
            throw "Bridge operation recovery found unknown dxgi.dll SHA: $currentSha"
        }
    }

    if ($restoreExists) {
        $backup = Assert-RavenBridgeChildPath $game (
            Join-Path $game ([string]$journal.restore_dll_relative))
        $backupManifest = Assert-RavenBridgeChildPath $game (
            Join-Path $game ([string]$journal.restore_manifest_relative))
        foreach ($path in @($backup,$backupManifest)) {
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "Bridge operation recovery backup missing: $path"
            }
        }
        if ((Get-RavenBridgeHash $backup) -ne $restoreSha) {
            throw 'Bridge operation recovery backup DLL SHA changed.'
        }
        $previous = Get-Content -LiteralPath $backupManifest -Raw | ConvertFrom-Json
        [void](Assert-RavenBridgeOwnedManifest -Manifest $previous -ExpectedSha $restoreSha)

        if (-not $targetExists -or (Get-RavenBridgeHash $target) -ne $restoreSha) {
            Copy-RavenBridgeFileAtomic -Source $backup -Destination $target -ExpectedSha $restoreSha
        }
        $manifestCopyArgs = @{
            Source = $backupManifest
            Destination = $manifestPath
            ExpectedSha = Get-RavenBridgeHash $backupManifest
        }
        Copy-RavenBridgeFileAtomic @manifestCopyArgs

        $restored = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        [void](Assert-RavenBridgeOwnedManifest -Manifest $restored -ExpectedSha $restoreSha)
        if ((Get-RavenBridgeHash $target) -ne $restoreSha) {
            throw 'Bridge operation recovery did not restore previous DLL exactly.'
        }
    }
    else {
        if ($targetExists) {
            Remove-Item -LiteralPath $target -Force
        }
        if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
            $owned = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
            $ownedSha = Assert-RavenBridgeOwnedManifest -Manifest $owned
            if ($ownedSha -ne $operationSha) {
                throw 'Bridge operation recovery found unexpected active manifest.'
            }
            Remove-Item -LiteralPath $manifestPath -Force
        }
        if ((Test-Path -LiteralPath $target) -or
            (Test-Path -LiteralPath $manifestPath)) {
            throw 'Bridge operation recovery expected owned pair to be absent.'
        }
    }

    Remove-Item -LiteralPath $operationPath -Force
    if (Test-Path -LiteralPath $operationPath) {
        throw 'Bridge operation journal could not be removed after recovery.'
    }

    Write-Host (
        "RAVEN_NATIVE_BRIDGE_OPERATION_RECOVERED operation=$($journal.operation) " +
        "restore_previous=$($restoreExists.ToString().ToLowerInvariant())")
    return [pscustomobject]@{
        Recovered = $true
        Operation = [string]$journal.operation
        RestoredPrevious = $restoreExists
    }
}
