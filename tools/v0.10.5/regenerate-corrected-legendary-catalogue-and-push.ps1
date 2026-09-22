[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$ExpectedBranch = 'codex/collectible-legendary-chests'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $RepoRoot
$branch = (& git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) { throw "Wrong branch '$branch'; expected '$ExpectedBranch'." }
if (@(& git status --porcelain).Count -gt 0) { throw 'Working tree must be clean before catalogue regeneration.' }
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) { throw 'Close God of War before static catalogue regeneration.' }

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

$Generator = Join-Path $RepoRoot 'tools\v0.10.5\collectible_catalogue.py'
$CatalogueTests = Join-Path $RepoRoot 'tools\v0.10.5\test_collectible_catalogue.py'
$LegendaryTests = Join-Path $RepoRoot 'tools\v0.10.5\test_legendary_chest_identity.py'
$StaticResolver = Join-Path $RepoRoot 'tools\v0.10.5\resolve-legendary-serialized-identities-static.py'
$IdentityHelper = Join-Path $RepoRoot 'tools\v0.10.5\legendary_chest_identity.py'
$RavenGuard = Join-Path $RepoRoot 'tools\v0.10.5\test-raven-frozen-baseline.ps1'
$CatalogueRel = 'config/collectibles/v0.10.5/all-collectibles.json'
$AuditRel = 'docs/research/all-collectibles-native-audit.json'
$Catalogue = Join-Path $RepoRoot ($CatalogueRel -replace '/', [IO.Path]::DirectorySeparatorChar)
$Audit = Join-Path $RepoRoot ($AuditRel -replace '/', [IO.Path]::DirectorySeparatorChar)

foreach ($required in @($Generator,$CatalogueTests,$LegendaryTests,$StaticResolver,$IdentityHelper,$RavenGuard,$Catalogue,$Audit)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}
foreach ($pythonFile in @($Generator,$CatalogueTests,$LegendaryTests,$StaticResolver,$IdentityHelper)) {
    & $python.Source -c "import py_compile,sys; py_compile.compile(sys.argv[1], doraise=True)" $pythonFile
    if ($LASTEXITCODE -ne 0) { throw "Python syntax validation failed: $pythonFile" }
}
& pwsh -NoProfile -ExecutionPolicy Bypass -File $RavenGuard
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven baseline guard failed.' }

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeEvidence = "archive/field-logs/source-scans/legendary-catalogue-regeneration-$stamp"
$evidence = Join-Path $RepoRoot ($relativeEvidence -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$console = Join-Path $evidence 'console-log.txt'
$resultFile = Join-Path $evidence 'result.txt'
$beforeCatalogue = (Get-FileHash -LiteralPath $Catalogue -Algorithm SHA256).Hash.ToLowerInvariant()
$beforeAudit = (Get-FileHash -LiteralPath $Audit -Algorithm SHA256).Hash.ToLowerInvariant()
$exitCode = 0
$failureMessage = ''
Start-Transcript -LiteralPath $console -Force | Out-Null
try {
    Write-Host 'CORRECTED LEGENDARY CATALOGUE REGENERATION' -ForegroundColor Cyan
    $genArgs = @($Generator,'--game-root',$GameRoot,'--output',$CatalogueRel,'--audit',$AuditRel)
    & $python.Source @genArgs
    if ($LASTEXITCODE -ne 0) { throw "Catalogue generator failed with exit code $LASTEXITCODE." }
    & $python.Source $CatalogueTests
    if ($LASTEXITCODE -ne 0) { throw "Catalogue tests failed with exit code $LASTEXITCODE." }
    & $python.Source $LegendaryTests
    if ($LASTEXITCODE -ne 0) { throw "Legendary identity tests failed with exit code $LASTEXITCODE." }
    $verifyScript = Join-Path $evidence 'verify.py'
    @(
'import collections, json, pathlib, sys'
'root = pathlib.Path(sys.argv[1])'
'catalogue = json.loads((root / "config/collectibles/v0.10.5/all-collectibles.json").read_text(encoding="utf-8"))'
'audit = json.loads((root / "docs/research/all-collectibles-native-audit.json").read_text(encoding="utf-8"))'
'rows = [r for r in catalogue["collectibles"] if r["family"] == "legendary_chest"]'
'elig = collections.Counter(r["production_eligibility"] for r in rows)'
'cls = collections.Counter(r["native_classification"] for r in rows)'
'expected_elig = {"tracked_collectible":33,"exclude_trial_reward":27,"exclude_non_map_counted":2,"unresolved":2}'
'expected_cls = {"tracked_legendary":33,"trial_reward":27,"non_map_counted_physical":2,"unresolved_nontracked":2}'
'assert dict(elig) == expected_elig, (elig, expected_elig)'
'assert dict(cls) == expected_cls, (cls, expected_cls)'
'tracked = [r for r in rows if r["production_eligibility"] == "tracked_collectible"]'
'assert len(tracked) == 33'
'parents = collections.Counter(r["progression"].get("parent_quest") for r in tracked)'
'targets = {k:v["target"] for k,v in audit["tracked_summary_targets"].items() if k.startswith("RegionSummary_LegendaryChest_Parent_")}'
'assert None not in parents'
'assert dict(parents) == targets, (dict(parents), targets)'
'by_id = {r["catalogue_id"]:r for r in rows}'
'required = {"legendary_chest_d0b93e274754785e08235285bd6b78f2":"RegionSummary_LegendaryChest_Parent_TyrsVault","legendary_chest_f714d2d845a3dd9e28808db4655e757f":"RegionSummary_LegendaryChest_Parent_TheHallofTyr"}'
'for cid,parent in required.items():'
'    row = by_id[cid]'
'    assert row["production_eligibility"] == "tracked_collectible"'
'    assert row["progression"]["parent_quest"] == parent'
'for cid in {"legendary_chest_3c05899e46a619015d4cfb995fb61be0","legendary_chest_8266c175474b43a4d44938a75e21329d"}:'
'    row = by_id[cid]'
'    assert row["production_eligibility"] == "exclude_non_map_counted"'
'    assert row["progression"].get("parent_quest") is None'
'print("LEGENDARY_CATALOGUE_PARTITION_VERIFIED tracked=33 trial=27 non_map_counted=2 unresolved=2")'
    ) | Set-Content -LiteralPath $verifyScript -Encoding UTF8
    & $python.Source $verifyScript $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw 'Corrected Legendary catalogue verification failed.' }
    $afterCatalogue = (Get-FileHash -LiteralPath $Catalogue -Algorithm SHA256).Hash.ToLowerInvariant()
    $afterAudit = (Get-FileHash -LiteralPath $Audit -Algorithm SHA256).Hash.ToLowerInvariant()
    @(
        'result=CORRECTED_LEGENDARY_CATALOGUE_REGENERATED'
        'tracked=33'
        'trial_reward=27'
        'exclude_non_map_counted=2'
        'unresolved=2'
        'native_target_total=33'
        "catalogue_sha256_before=$beforeCatalogue"
        "catalogue_sha256_after=$afterCatalogue"
        "audit_sha256_before=$beforeAudit"
        "audit_sha256_after=$afterAudit"
        'game_process_accessed=false'
        'save_or_progression_written=false'
        'raven_runtime_modified=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
} catch {
    $exitCode = 1
    $failureMessage = $_.Exception.Message
    @('result=CORRECTED_LEGENDARY_CATALOGUE_REGENERATION_FAILED',"reason=$failureMessage") | Set-Content -LiteralPath $resultFile -Encoding UTF8
} finally {
    Stop-Transcript | Out-Null
}

& git add -- $CatalogueRel $AuditRel
& git add -f -- $relativeEvidence
if ($LASTEXITCODE -ne 0) { throw 'git add regenerated catalogue evidence failed.' }
$message = if ($exitCode -eq 0) { "research(v0.10.5): regenerate corrected Legendary catalogue $stamp" } else { "research(v0.10.5): archive Legendary catalogue regeneration failure $stamp" }
& git commit -m $message -- $CatalogueRel $AuditRel $relativeEvidence
if ($LASTEXITCODE -ne 0) { throw 'git commit regenerated catalogue failed.' }
& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push regenerated catalogue failed.' }
$head = (& git rev-parse HEAD).Trim()
if ($exitCode -ne 0) { throw "Corrected Legendary catalogue regeneration failed; evidence pushed in $head. $failureMessage" }
Write-Host ''
Write-Host "CORRECTED_LEGENDARY_CATALOGUE_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeEvidence"
