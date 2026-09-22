[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$ExpectedBranch = 'codex/collectible-legendary-chests',
    [string]$ExpectedSha256 = 'aec578e773898a1e60d5ccedd0df08e35b12ab54e4d26f4cd90740948430c2a0',
    [long]$ExpectedBytes = 74128,
    [string]$ExpectedSteamBuildId = '11168363'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $RepoRoot

$branch = (& git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) { throw "Wrong branch '$branch'; expected '$ExpectedBranch'." }
$dirty = @(& git status --porcelain)
if ($dirty.Count -gt 0) {
    Write-Host 'Working tree is not clean:' -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "  $_" }
    throw 'Working tree must be clean before the Steam-native compatibility audit.'
}
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War before the Steam-native compatibility audit.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

$Mapmaster = Join-Path $GameRoot 'exec\dc\pc_le\mapmaster.dcb'
if (-not (Test-Path -LiteralPath $Mapmaster -PathType Leaf)) { throw "Missing installed mapmaster: $Mapmaster" }
$item = Get-Item -LiteralPath $Mapmaster
$sha = (Get-FileHash -LiteralPath $Mapmaster -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "STEAM_NATIVE_CANDIDATE bytes=$($item.Length) sha=$sha"
if ($item.Length -ne $ExpectedBytes -or $sha -ne $ExpectedSha256.ToLowerInvariant()) {
    throw "Installed mapmaster does not match the Steam-verified candidate profile. Expected sha=$ExpectedSha256 bytes=$ExpectedBytes; got sha=$sha bytes=$($item.Length)."
}

$RecoveryRoot = Join-Path $RepoRoot 'build\legendary-pristine-mapmaster-recovery'
$ActivePath = Join-Path $RecoveryRoot 'active.json'
if (-not (Test-Path -LiteralPath $ActivePath -PathType Leaf)) {
    throw "No active Steam-verify recovery transaction exists: $ActivePath"
}
$active = Get-Content -LiteralPath $ActivePath -Raw | ConvertFrom-Json
$ManifestPath = [string]$active.manifest
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "Missing recovery manifest: $ManifestPath" }
$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ([IO.Path]::GetFullPath([string]$manifest.game_root) -ne [IO.Path]::GetFullPath($GameRoot)) {
    throw 'Active Steam-verify recovery transaction belongs to a different game root.'
}
$BackupDcbDir = [string]$manifest.backup_dcb_dir
if (-not (Test-Path -LiteralPath $BackupDcbDir -PathType Container)) {
    throw "Preserved pre-Steam DCB backup is missing: $BackupDcbDir"
}

$SteamApps = Split-Path -Parent (Split-Path -Parent $GameRoot)
$AppManifest = Join-Path $SteamApps 'appmanifest_1593500.acf'
$steamBuildId = $null
if (Test-Path -LiteralPath $AppManifest -PathType Leaf) {
    $buildLine = Select-String -LiteralPath $AppManifest -Pattern '"buildid"\s+"([0-9]+)"' | Select-Object -First 1
    if ($buildLine -and $buildLine.Matches.Count -gt 0) { $steamBuildId = $buildLine.Matches[0].Groups[1].Value }
}
Write-Host "STEAM_BUILD_ID $steamBuildId"
if ($steamBuildId -ne $ExpectedSteamBuildId) {
    throw "Steam build ID mismatch. Expected $ExpectedSteamBuildId, got '$steamBuildId'."
}

$Generator = Join-Path $RepoRoot 'tools\v0.10.5\collectible_catalogue.py'
$Canonical = Join-Path $RepoRoot 'config\collectibles\v0.10.5\all-collectibles.json'
$CanonicalAudit = Join-Path $RepoRoot 'docs\research\all-collectibles-native-audit.json'
foreach ($required in @($Generator,$Canonical,$CanonicalAudit)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeEvidence = "archive/field-logs/source-scans/legendary-steam-mapmaster-compatibility-$stamp"
$Evidence = Join-Path $RepoRoot ($relativeEvidence -replace '/', [IO.Path]::DirectorySeparatorChar)
$Scratch = Join-Path $RepoRoot "build\legendary-steam-mapmaster-compatibility-$stamp"
New-Item -ItemType Directory -Force -Path $Evidence,$Scratch | Out-Null
$CandidateCatalogue = Join-Path $Scratch 'candidate-catalogue.json'
$CandidateAudit = Join-Path $Scratch 'candidate-audit.json'
$CompareScript = Join-Path $Scratch 'compare.py'
$CompareJson = Join-Path $Evidence 'comparison.json'
$Console = Join-Path $Evidence 'console-log.txt'
$Result = Join-Path $Evidence 'result.txt'
$Profile = Join-Path $Evidence 'source-profile.json'

@'
import collections, hashlib, json, pathlib, sys
canonical_path, candidate_path, candidate_audit_path, output_path = map(pathlib.Path, sys.argv[1:5])
canonical = json.loads(canonical_path.read_text(encoding='utf-8'))
candidate = json.loads(candidate_path.read_text(encoding='utf-8'))
audit = json.loads(candidate_audit_path.read_text(encoding='utf-8'))

def rows(doc):
    return {r['catalogue_id']: r for r in doc['collectibles'] if r['family'] == 'legendary_chest'}

def projection(row):
    return {
        'catalogue_id': row['catalogue_id'],
        'production_eligibility': row.get('production_eligibility'),
        'native_classification': row.get('native_classification'),
        'parent_quest': row.get('progression', {}).get('parent_quest'),
        'realm': row.get('realm'),
        'region': row.get('region'),
        'instance_guid': row.get('native', {}).get('instance_guid'),
        'placement_object_name': row.get('native', {}).get('placement_object_name'),
        'position_world': row.get('marker', {}).get('position_world'),
        'position_map': row.get('marker', {}).get('position_map'),
    }

c = rows(canonical)
n = rows(candidate)
missing = sorted(set(c) - set(n))
extra = sorted(set(n) - set(c))
mismatches = []
for cid in sorted(set(c) & set(n)):
    cp, np = projection(c[cid]), projection(n[cid])
    if cp != np:
        mismatches.append({'catalogue_id': cid, 'canonical': cp, 'candidate': np})

elig = collections.Counter(r.get('production_eligibility') for r in n.values())
cls = collections.Counter(r.get('native_classification') for r in n.values())
expected_elig = {'tracked_collectible': 33, 'exclude_trial_reward': 27, 'exclude_non_map_counted': 2, 'unresolved': 2}
expected_cls = {'tracked_legendary': 33, 'trial_reward': 27, 'non_map_counted_physical': 2, 'unresolved_nontracked': 2}
tracked_target = audit.get('native_tracked_target_totals', {}).get('legendary_chest')
map_evidence = audit.get('native_evidence', {}).get('mapmaster', {})
required = {
    'legendary_chest_d0b93e274754785e08235285bd6b78f2': 'RegionSummary_LegendaryChest_Parent_TyrsVault',
    'legendary_chest_f714d2d845a3dd9e28808db4655e757f': 'RegionSummary_LegendaryChest_Parent_TheHallofTyr',
}
excluded = {
    'legendary_chest_3c05899e46a619015d4cfb995fb61be0',
    'legendary_chest_8266c175474b43a4d44938a75e21329d',
}
special_errors = []
for cid, parent in required.items():
    row = n.get(cid)
    if not row or row.get('production_eligibility') != 'tracked_collectible' or row.get('progression', {}).get('parent_quest') != parent:
        special_errors.append(cid)
for cid in excluded:
    row = n.get(cid)
    if not row or row.get('production_eligibility') != 'exclude_non_map_counted' or row.get('progression', {}).get('parent_quest') is not None:
        special_errors.append(cid)

passed = (
    not missing and not extra and not mismatches and
    dict(elig) == expected_elig and dict(cls) == expected_cls and
    tracked_target == 33 and not special_errors
)
report = {
    'result': 'PASS_EQUIVALENT_LEGENDARY_NATIVE_PROFILE' if passed else 'FAIL_LEGENDARY_NATIVE_PROFILE_MISMATCH',
    'candidate_legendary_rows': len(n),
    'missing_catalogue_ids': missing,
    'extra_catalogue_ids': extra,
    'projection_mismatches': mismatches,
    'production_eligibility_counts': dict(elig),
    'native_classification_counts': dict(cls),
    'native_tracked_target_total': tracked_target,
    'special_identity_errors': sorted(set(special_errors)),
    'candidate_mapmaster_evidence': map_evidence,
    'canonical_projection_sha256': hashlib.sha256(json.dumps([projection(c[k]) for k in sorted(c)], sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
    'candidate_projection_sha256': hashlib.sha256(json.dumps([projection(n[k]) for k in sorted(n)], sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
}
output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2, sort_keys=True))
raise SystemExit(0 if passed else 1)
'@ | Set-Content -LiteralPath $CompareScript -Encoding UTF8

$exitCode = 0
$failureMessage = ''
Start-Transcript -LiteralPath $Console -Force | Out-Null
try {
    Write-Host 'CURRENT STEAM MAPMASTER -> LEGENDARY COMPATIBILITY AUDIT' -ForegroundColor Cyan
    $candidateOutputRel = [IO.Path]::GetRelativePath($RepoRoot, $CandidateCatalogue).Replace('\','/')
    $candidateAuditRel = [IO.Path]::GetRelativePath($RepoRoot, $CandidateAudit).Replace('\','/')
    & $python.Source $Generator --game-root $GameRoot --mapmaster $Mapmaster --output $candidateOutputRel --audit $candidateAuditRel
    if ($LASTEXITCODE -ne 0) { throw "Catalogue extraction from current Steam-native source failed with exit code $LASTEXITCODE." }

    & $python.Source $CompareScript $Canonical $CandidateCatalogue $CandidateAudit $CompareJson
    if ($LASTEXITCODE -ne 0) { throw 'Current Steam-native mapmaster does not reproduce the accepted Legendary catalogue projection.' }

    $candidateAuditObject = Get-Content -LiteralPath $CandidateAudit -Raw | ConvertFrom-Json
    $mapEvidence = $candidateAuditObject.native_evidence.mapmaster
    if (([string]$mapEvidence.sha256).ToLowerInvariant() -ne $ExpectedSha256.ToLowerInvariant() -or [long]$mapEvidence.bytes -ne $ExpectedBytes) {
        throw "Candidate audit mapmaster provenance mismatch: sha=$($mapEvidence.sha256) bytes=$($mapEvidence.bytes)"
    }

    $CacheDir = Join-Path $RepoRoot 'build\native-source-cache'
    $CachePath = Join-Path $CacheDir 'mapmaster.dcb'
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    Copy-Item -LiteralPath $Mapmaster -Destination $CachePath -Force
    $cacheItem = Get-Item -LiteralPath $CachePath
    $cacheSha = (Get-FileHash -LiteralPath $CachePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($cacheItem.Length -ne $ExpectedBytes -or $cacheSha -ne $ExpectedSha256.ToLowerInvariant()) {
        throw 'Compatible Steam-native mapmaster cache copy failed validation.'
    }

    [ordered]@{
        profile = 'steam-build-11168363-native-mapmaster'
        compatibility = 'PASS_EQUIVALENT_LEGENDARY_NATIVE_PROFILE'
        steam_build_id = $steamBuildId
        bytes = [long]$item.Length
        sha256 = $sha
        source = [IO.Path]::GetFullPath($Mapmaster)
        cache = [IO.Path]::GetFullPath($CachePath)
        historical_catalogue_source = [ordered]@{
            bytes = 75872
            sha256 = '1e1d5086815bc8553490bff915fea210a8be4f80ce6c88b418b62d7050690a31'
        }
        comparison = 'Legendary production projection exactly matches accepted canonical catalogue'
        audited_utc = (Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Profile -Encoding UTF8

    @(
        'result=PASS_EQUIVALENT_LEGENDARY_NATIVE_PROFILE'
        "steam_build_id=$steamBuildId"
        "native_mapmaster_sha256=$sha"
        "native_mapmaster_bytes=$($item.Length)"
        'tracked=33'
        'trial_reward=27'
        'exclude_non_map_counted=2'
        'unresolved=2'
        'native_target_total=33'
        'canonical_projection_match=true'
        "cache=$CachePath"
        "preserved_pre_steam_backup=$BackupDcbDir"
        'pre_steam_backup_restored=false'
        'game_files_written=false'
        'save_or_progression_written=false'
    ) | Set-Content -LiteralPath $Result -Encoding UTF8
    Write-Host 'STEAM_NATIVE_LEGENDARY_COMPATIBILITY_PASS' -ForegroundColor Green
    Write-Host "  cache=$CachePath"
} catch {
    $exitCode = 1
    $failureMessage = $_.Exception.Message
    @(
        'result=FAIL_LEGENDARY_NATIVE_PROFILE_COMPATIBILITY'
        "steam_build_id=$steamBuildId"
        "native_mapmaster_sha256=$sha"
        "native_mapmaster_bytes=$($item.Length)"
        "reason=$failureMessage"
        'cache_promoted=false'
        'pre_steam_backup_restored=false'
    ) | Set-Content -LiteralPath $Result -Encoding UTF8
} finally {
    Stop-Transcript | Out-Null
}

& git add -f -- $relativeEvidence
if ($LASTEXITCODE -ne 0) { throw 'git add compatibility evidence failed.' }
$message = if ($exitCode -eq 0) {
    "research(v0.10.5): prove Steam mapmaster Legendary compatibility $stamp"
} else {
    "research(v0.10.5): archive Steam mapmaster compatibility failure $stamp"
}
& git commit -m $message -- $relativeEvidence
if ($LASTEXITCODE -ne 0) { throw 'git commit compatibility evidence failed.' }
& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push compatibility evidence failed.' }
$head = (& git rev-parse HEAD).Trim()
if ($exitCode -ne 0) {
    throw "Steam-native Legendary compatibility audit failed; evidence pushed in $head. $failureMessage"
}
Write-Host ''
Write-Host "STEAM_NATIVE_LEGENDARY_COMPATIBILITY_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeEvidence"
