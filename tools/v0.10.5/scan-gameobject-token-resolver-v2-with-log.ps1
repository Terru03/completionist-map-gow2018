param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relative = "archive/field-logs/source-scans/gameobject-token-resolver-v2-$stamp"
$outDir = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$json = Join-Path $outDir 'gameobject-token-resolver.json'
$text = Join-Path $outDir 'gameobject-token-resolver.txt'
$pythonOutput = Join-Path $outDir 'python-output.txt'
$patchedScanner = Join-Path $env:TEMP ("completionist-token-resolver-$stamp.py")
$published = $false
$transcript = $false

function Publish([string]$Result) {
    if ($script:published) { return }
    if ($script:transcript) { Stop-Transcript | Out-Null; $script:transcript = $false }
    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        'source_hashes_unchanged=true'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
        'scan_only=true'
        'resolver_leaf_fallback=true'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8
    & git add -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relative
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Archive GameObject token resolver v2 scan $stamp" -- $relative | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin "HEAD:$expectedBranch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) { throw 'git diff failed.' }
    $script:published = $true
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true
    Write-Host '=== Completionist Map exact GameObject token resolver provenance scan v2 ==='
    Write-Host 'Read-only static GoW.exe analysis. 0x4EF0B0 is treated as an exact leaf entry when .pdata is absent.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing staged changes: $($staged -join ', ')" }

    $scanner = Join-Path $repo 'tools\v0.10.5\analyze-gameobject-token-resolver.py'
    $exe = Join-Path $GameRoot 'GoW.exe'
    if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) { throw 'Scanner missing.' }
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'GoW.exe missing.' }

    $source = [IO.File]::ReadAllText($scanner, [Text.Encoding]::UTF8)
    $old = "    resolver_fn=pe.function_for(RESOLVER_RVA)`r`n    if resolver_fn is None: raise RuntimeError(`"No pdata function contains resolver RVA 0x4EF0B0`")"
    if (-not $source.Contains($old)) {
        $old = "    resolver_fn=pe.function_for(RESOLVER_RVA)`n    if resolver_fn is None: raise RuntimeError(`"No pdata function contains resolver RVA 0x4EF0B0`")"
    }
    if (-not $source.Contains($old)) { throw 'Expected resolver .pdata guard not found in analyzer.' }

    $new = "    resolver_fn=pe.function_for(RESOLVER_RVA)`n    if resolver_fn is None:`n        resolver_fn={`"begin`":RESOLVER_RVA,`"end`":min(RESOLVER_RVA+0x200,pe.size_of_image),`"unwind`":None}"
    $patched = $source.Replace($old, $new)
    [IO.File]::WriteAllText($patchedScanner, $patched, (New-Object Text.UTF8Encoding($false)))

    $python = (Get-Command python.exe -ErrorAction SilentlyContinue)
    if ($null -eq $python) { $python = (Get-Command python -ErrorAction SilentlyContinue) }
    if ($null -eq $python) { throw 'Python executable not found.' }

    $cmd = '"{0}" "{1}" --game-root "{2}" --output-json "{3}" --output-text "{4}" > "{5}" 2>&1' -f $python.Source, $patchedScanner, $GameRoot, $json, $text, $pythonOutput
    & cmd.exe /d /s /c $cmd
    $code = $LASTEXITCODE
    if (Test-Path -LiteralPath $pythonOutput) { Get-Content -LiteralPath $pythonOutput | Out-Host }
    if ($code -ne 0) { throw "Analyzer exited with code $code. Full traceback is archived in python-output.txt." }

    Publish 'SCAN_PASSED'
    Write-Host 'GAMEOBJECT_TOKEN_RESOLVER_V2_SCAN_PASSED_AND_PUSHED' -ForegroundColor Green
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish 'SCAN_FAILED' } catch {}
    exit 1
}
finally {
    if (Test-Path -LiteralPath $patchedScanner) { Remove-Item -LiteralPath $patchedScanner -Force -ErrorAction SilentlyContinue }
    if ($transcript) { try { Stop-Transcript | Out-Null } catch {} }
}
