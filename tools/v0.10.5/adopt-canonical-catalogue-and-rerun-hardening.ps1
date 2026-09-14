param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-ravens-release-candidate'
$target = 'catalogue/odins-ravens.json'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/all-ravens-catalogue-adopt-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$transcriptStarted = $false
$published = $false
$catalogueCommitted = $false

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Write-Result([string]$Result) {
    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        "target=$target"
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
        'native_game_data_read_only=true'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8
}

function Publish-FailureLog {
    if ($script:published -or $script:catalogueCommitted) { return }
    $script:published = $true
    Stop-LocalTranscript
    Write-Result 'CATALOGUE_ADOPTION_FAILED'
    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'Unable to stage adoption failure log.' }
    & git commit -m "Archive failed Raven catalogue adoption $stamp" -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'Unable to commit adoption failure log.' }
    & git push origin "HEAD:$expectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to push adoption failure log.' }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map canonical Raven catalogue adoption ==='
    Write-Host 'This verifies the existing local catalogue edit against a fresh native-data build before committing it.'
    Write-Host 'God of War is not launched; active saves are never opened.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) {
        throw "Wrong branch. Expected '$expectedBranch', found '$branch'."
    }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) {
        throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')"
    }

    $status = @(& git status --porcelain -- $target)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect catalogue status.' }
    if ($status.Count -ne 1 -or $status[0].TrimEnd() -ne "M $target") {
        # Porcelain has two status columns; an unstaged tracked edit renders as leading-space + M.
        if ($status.Count -ne 1 -or $status[0] -ne " M $target") {
            throw "Expected exactly one unstaged catalogue edit; found: $($status -join '; ')"
        }
    }

    $numstat = (& git diff --numstat -- $target).Trim()
    $numstat | Set-Content -LiteralPath (Join-Path $logDir 'catalogue-numstat.txt') -Encoding UTF8
    if ($numstat -notmatch '^53\s+0\s+catalogue/odins-ravens\.json$') {
        throw "Catalogue diff is not the expected 53-addition/0-deletion shape: $numstat"
    }

    $diffLines = @(& git diff --unified=0 -- $target)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect catalogue diff.' }
    $diffLines | Set-Content -LiteralPath (Join-Path $logDir 'catalogue-working.diff') -Encoding UTF8
    $added = @($diffLines | Where-Object { $_ -match '^\+' -and $_ -notmatch '^\+\+\+' })
    $removed = @($diffLines | Where-Object { $_ -match '^-' -and $_ -notmatch '^---' })
    if ($added.Count -ne 53 -or $removed.Count -ne 0) {
        throw "Unexpected catalogue patch shape: added=$($added.Count) removed=$($removed.Count)"
    }
    $badAdded = @($added | Where-Object { $_ -notmatch '^\+\s+"coordinate_wad": "WAD_[A-Za-z0-9_]+",$' })
    if ($badAdded.Count -gt 0) {
        throw "Catalogue contains additions other than coordinate_wad rows: $($badAdded -join '; ')"
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $python) { throw 'Python executable not found on PATH.' }

    $extractor = Join-Path $repo 'tools/v0.10.5/extract-native-raven-catalogue.py'
    if (-not (Test-Path -LiteralPath $extractor -PathType Leaf)) { throw "Missing extractor: $extractor" }
    $gameRoot = 'G:/SteamLibrary/steamapps/common/GodOfWar'
    if (-not (Test-Path -LiteralPath $gameRoot -PathType Container)) { throw "God of War fixture not found: $gameRoot" }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("completionist-raven-catalogue-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    try {
        $generatedCatalogue = Join-Path $tempRoot 'odins-ravens.json'
        $generatedAudit = Join-Path $tempRoot 'audit.json'
        Write-Host '=== REBUILD CANONICAL CATALOGUE FROM NATIVE GAME DATA ==='
        & $python.Source $extractor --game-root $gameRoot --catalogue $generatedCatalogue --audit $generatedAudit 2>&1 |
            Tee-Object -FilePath (Join-Path $logDir 'extractor-output.txt')
        if ($LASTEXITCODE -ne 0) { throw "Native catalogue extraction failed with exit code $LASTEXITCODE" }

        $workText = [IO.File]::ReadAllText((Join-Path $repo $target)).Replace("`r`n", "`n")
        $generatedText = [IO.File]::ReadAllText($generatedCatalogue).Replace("`r`n", "`n")
        if ($workText -ne $generatedText) {
            throw 'Local catalogue edit does not exactly equal the canonical catalogue rebuilt from current native game data.'
        }

        $audit = Get-Content -LiteralPath $generatedAudit -Raw | ConvertFrom-Json
        if ([int]$audit.expected_native_object_count -ne 53 -or [int]$audit.native_labor_target_count -ne 51) {
            throw 'Canonical audit object/labor counts changed unexpectedly.'
        }
        if ($audit.ready_for_runtime_test -ne $false) {
            throw 'Canonical audit unexpectedly opened the unloaded-state runtime gate.'
        }

        @(
            'canonical_match=true'
            'added_coordinate_wad_rows=53'
            'deleted_rows=0'
            "expected_native_object_count=$($audit.expected_native_object_count)"
            "native_labor_target_count=$($audit.native_labor_target_count)"
            "ready_for_runtime_test=$($audit.ready_for_runtime_test)"
        ) | Set-Content -LiteralPath (Join-Path $logDir 'canonical-verification.txt') -Encoding UTF8
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
    }

    Write-Host 'CANONICAL_CATALOGUE_VERIFIED'
    Stop-LocalTranscript
    Write-Result 'CATALOGUE_ADOPTION_PASSED'

    & git add -- $target $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'Unable to stage the verified catalogue and adoption log.' }
    & git diff --cached --quiet -- $target
    if ($LASTEXITCODE -ne 1) { throw 'Verified catalogue was not staged as a change.' }

    & git commit -m 'Adopt canonical Raven coordinate WAD catalogue' -- $target $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'Unable to commit verified canonical catalogue.' }
    $catalogueCommitted = $true

    & git push origin "HEAD:$expectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to push verified canonical catalogue.' }
    Write-Host 'CANONICAL_CATALOGUE_COMMITTED_AND_PUSHED'

    $runner = Join-Path $repo 'tools/v0.10.5/run-all-ravens-hardening-with-log.ps1'
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw "Missing hardening runner: $runner" }
    Write-Host '=== RERUN ALL-RAVENS HARDENING ==='
    & pwsh.exe -NoProfile -ExecutionPolicy Bypass -File $runner
    $hardeningCode = $LASTEXITCODE
    if ($hardeningCode -ne 0) {
        throw "All-Ravens hardening rerun failed with exit code $hardeningCode. Its self-published log contains the failure."
    }

    Write-Host 'CANONICAL_CATALOGUE_ADOPTED_AND_HARDENING_PASSED'
    exit 0
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "CATALOGUE_ADOPTION_OR_HARDENING_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-FailureLog } catch {
        Write-Host "ADOPTION_LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 1
}
finally {
    Stop-LocalTranscript
}
