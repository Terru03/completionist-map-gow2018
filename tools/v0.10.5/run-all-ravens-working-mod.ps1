param(
    [string]$GameRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$installer = Join-Path $PSScriptRoot 'install-all-ravens-working-mod.ps1'
$archiveRoot = Join-Path $repo 'archive\field-logs\runtime'
$launcherRunId = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$launcherRelativeDir = "archive/field-logs/runtime/all-ravens-launcher-$launcherRunId"
$launcherDir = Join-Path $repo ("archive\field-logs\runtime\all-ravens-launcher-" + $launcherRunId)
$launcherLog = Join-Path $launcherDir 'launcher.txt'
$launcherResult = Join-Path $launcherDir 'result.json'

function Invoke-Git {
    param([string[]]$Arguments, [switch]$AllowFailure)
    & git -C $repo @Arguments 2>&1 | Tee-Object -FilePath $launcherLog -Append | Out-Host
    $code = $LASTEXITCODE
    if (-not $AllowFailure -and $code -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $code"
    }
    return $code
}

function Get-Branch {
    $value = (& git -C $repo branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value)) {
        throw 'Could not determine current Git branch.'
    }
    return $value
}

function Get-Head {
    $value = (& git -C $repo rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $value -notmatch '^[0-9a-fA-F]{40}$') {
        throw 'Could not determine Git HEAD.'
    }
    return $value.ToLowerInvariant()
}

function Assert-Parses {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing script: $Path"
    }
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $Path,
        [ref]$tokens,
        [ref]$errors
    )
    if (@($errors).Count -gt 0) {
        $details = (@($errors | ForEach-Object {
            "line $($_.Extent.StartLineNumber): $($_.Message)"
        }) -join ' | ')
        throw "PowerShell parse failure in $Path: $details"
    }
}

function Get-UnpublishedRavenRunDirs {
    if (-not (Test-Path -LiteralPath $archiveRoot -PathType Container)) { return @() }

    $dirs = @(
        Get-ChildItem -LiteralPath $archiveRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like 'all-ravens-working-install-*' } |
            Sort-Object Name
    )

    $result = New-Object System.Collections.Generic.List[object]
    foreach ($dir in $dirs) {
        $relative = [IO.Path]::GetRelativePath($repo, $dir.FullName).Replace('\','/')
        $status = @(& git -C $repo status --porcelain --untracked-files=all -- $relative)
        if ($LASTEXITCODE -ne 0) {
            throw "Could not inspect Git state for $relative"
        }
        if (@($status).Count -gt 0) {
            $result.Add([pscustomobject]@{ FullName = $dir.FullName; Relative = $relative; Name = $dir.Name })
        }
    }
    return @($result)
}

function Publish-Paths {
    param(
        [string[]]$Paths,
        [string]$Message
    )

    $pathsToPublish = @($Paths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
    if ($pathsToPublish.Count -eq 0) { return $null }

    & git -C $repo add -- @pathsToPublish 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage Raven launcher artifacts.' }

    & git -C $repo diff --cached --quiet --ignore-submodules -- @pathsToPublish
    if ($LASTEXITCODE -eq 0) { return $null }

    & git -C $repo commit -m $Message -- @pathsToPublish 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Could not commit Raven launcher artifacts.' }

    $commit = Get-Head
    $pushed = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & git -C $repo push origin $expectedBranch 2>&1 | Out-Host
        if ($LASTEXITCODE -eq 0) {
            $pushed = $true
            break
        }
        Start-Sleep -Seconds (2 * $attempt)
    }
    if (-not $pushed) {
        throw "Raven launcher artifact commit $commit could not be pushed after 3 attempts."
    }
    return $commit
}

New-Item -ItemType Directory -Force -Path $launcherDir | Out-Null
"launcher_run_id=$launcherRunId" | Set-Content -LiteralPath $launcherLog -Encoding UTF8
"started_utc=$((Get-Date).ToUniversalTime().ToString('o'))" | Add-Content -LiteralPath $launcherLog -Encoding UTF8

$branch = ''
$headAtStart = ''
$childExitCode = $null
$outcome = 'failed'
$errorText = $null
$salvagedBefore = @()
$salvagedAfter = @()
$publishedCommit = $null

try {
    $branch = Get-Branch
    if ($branch -ne $expectedBranch) {
        throw "Expected branch '$expectedBranch', got '$branch'."
    }
    $headAtStart = Get-Head
    "branch=$branch" | Add-Content -LiteralPath $launcherLog -Encoding UTF8
    "head_at_start=$headAtStart" | Add-Content -LiteralPath $launcherLog -Encoding UTF8

    $salvagedBefore = @(Get-UnpublishedRavenRunDirs)
    if ($salvagedBefore.Count -gt 0) {
        "salvaging_before=$($salvagedBefore.Relative -join ';')" | Add-Content -LiteralPath $launcherLog -Encoding UTF8
        $commit = Publish-Paths -Paths @($salvagedBefore.Relative) -Message "field: salvage orphaned all-Ravens run evidence $launcherRunId"
        if ($null -ne $commit) {
            "salvage_before_commit=$commit" | Add-Content -LiteralPath $launcherLog -Encoding UTF8
        }
    }

    Assert-Parses -Path $installer
    "installer_parse_preflight=passed" | Add-Content -LiteralPath $launcherLog -Encoding UTF8

    $pwsh = (Get-Command pwsh -ErrorAction Stop).Source
    $childArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$installer)
    if (-not [string]::IsNullOrWhiteSpace($GameRoot)) {
        $childArgs += @('-GameRoot',$GameRoot)
    }

    "child_command=$pwsh $($childArgs -join ' ')" | Add-Content -LiteralPath $launcherLog -Encoding UTF8
    & $pwsh @childArgs 2>&1 | Tee-Object -FilePath $launcherLog -Append | Out-Host
    $childExitCode = $LASTEXITCODE
    "child_exit_code=$childExitCode" | Add-Content -LiteralPath $launcherLog -Encoding UTF8

    if ($childExitCode -ne 0) {
        throw "All-Ravens installer child process failed with exit code $childExitCode."
    }

    $outcome = 'completed'
}
catch {
    $errorText = $_.Exception.ToString()
    "launcher_error=$($_.Exception.Message)" | Add-Content -LiteralPath $launcherLog -Encoding UTF8
}
finally {
    try {
        $salvagedAfter = @(Get-UnpublishedRavenRunDirs)
        if ($salvagedAfter.Count -gt 0) {
            "salvaging_after=$($salvagedAfter.Relative -join ';')" | Add-Content -LiteralPath $launcherLog -Encoding UTF8
            $commit = Publish-Paths -Paths @($salvagedAfter.Relative) -Message "field: salvage failed all-Ravens child evidence $launcherRunId"
            if ($null -ne $commit) {
                "salvage_after_commit=$commit" | Add-Content -LiteralPath $launcherLog -Encoding UTF8
            }
        }
    }
    catch {
        $salvageError = $_.Exception.ToString()
        "salvage_after_error=$($_.Exception.Message)" | Add-Content -LiteralPath $launcherLog -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($errorText)) { $errorText = $salvageError }
        else { $errorText += [Environment]::NewLine + $salvageError }
        $outcome = 'failed'
    }

    $result = [ordered]@{
        schema = 1
        launcher_run_id = $launcherRunId
        finished_utc = (Get-Date).ToUniversalTime().ToString('o')
        outcome = $outcome
        branch = $branch
        head_at_start = $headAtStart
        child_exit_code = $childExitCode
        installer = $installer
        salvaged_before = @($salvagedBefore | ForEach-Object { $_.Relative })
        salvaged_after = @($salvagedAfter | ForEach-Object { $_.Relative })
        error = $errorText
    }
    [IO.File]::WriteAllText(
        $launcherResult,
        (($result | ConvertTo-Json -Depth 6) + [Environment]::NewLine),
        (New-Object Text.UTF8Encoding($false))
    )

    try {
        $publishedCommit = Publish-Paths -Paths @($launcherRelativeDir) -Message "field: record all-Ravens launcher $outcome $launcherRunId"
    }
    catch {
        "launcher_publish_error=$($_.Exception.Message)" | Add-Content -LiteralPath $launcherLog -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($errorText)) { $errorText = $_.Exception.ToString() }
        else { $errorText += [Environment]::NewLine + $_.Exception.ToString() }
        $outcome = 'failed'
    }
}

if ($outcome -ne 'completed') {
    if ($null -ne $publishedCommit) {
        throw "All-Ravens launcher failed; launcher evidence was pushed in commit $publishedCommit. $errorText"
    }
    throw "All-Ravens launcher failed. $errorText"
}

Write-Host "COMPLETIONIST_MAP_ALL_RAVENS_LAUNCHER_RESULT_PUSHED $publishedCommit"
