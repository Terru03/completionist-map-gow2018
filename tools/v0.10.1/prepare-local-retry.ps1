$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installerPath = Join-Path $scriptDir 'install.ps1'

if (-not (Test-Path $installerPath)) {
    throw "Missing installer: $installerPath"
}

$text = [IO.File]::ReadAllText($installerPath)

$startMarker = '$IconRepo = ''Terru03/completionist-map-gow2018'''
$endMarker = 'function Export-CompletionistSquarePng('
$start = $text.IndexOf($startMarker, [StringComparison]::Ordinal)
$end = $text.IndexOf($endMarker, [StringComparison]::Ordinal)

if ($start -lt 0 -or $end -lt 0 -or $end -le $start) {
    throw 'Could not locate the v0.10.0 GitHub icon-fetch block. Refusing to modify install.ps1.'
}

$replacement = @'
$IconRoot = Join-Path $GameRoot 'mods\completionist-map\icons'
$IconConceptDir = Join-Path $IconRoot 'concepts'
$IconGeneratedDir = Join-Path $IconRoot 'generated'
$IconManifestPath = Join-Path $IconRoot 'manifest.json'

$CompletionistIconFiles = [ordered]@{
    'raven' = 'raven_concept_master.png'
    'nornir_chest' = 'nornir_chest_concept_master.png'
    'nornir_seal' = 'nornir_seal_concept_master.png'
    'nornir_bell' = 'nornir_bell_concept_master.png'
    'nornir_mechanism' = 'nornir_mechanism_concept_master.png'
    'lore_marker' = 'lore_marker_concept_master.png'
    'artefact' = 'artefact_concept_master.png'
    'legendary_chest' = 'legendary_chest_concept_master.png'
    'remaining_collectible' = 'remaining_collectible_concept_master.png'
    'player_marker' = 'player_marker_concept_master.png'
}

# v0.10.1 is network-independent. Prefer assets bundled beside install.ps1.
# When running directly from the cloned repository, fall back to repo/assets.
$IconSourceDir = Join-Path $PSScriptRoot 'assets\icons\concepts'
if (-not (Test-Path $IconSourceDir)) {
    $repoRootCandidate = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $repoAssetCandidate = Join-Path $repoRootCandidate 'assets\icons\concepts'
    if (Test-Path $repoAssetCandidate) {
        $IconSourceDir = $repoAssetCandidate
    }
}

if (-not (Test-Path $IconSourceDir)) {
    throw "Completionist icon masters were not found. Expected bundled or repository assets at: $IconSourceDir"
}

function Assert-CompletionistPng([string]$Path) {
    if (-not (Test-Path $Path)) {
        throw "Missing icon master: $Path"
    }

    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 8 -or
        $bytes[0] -ne 0x89 -or
        $bytes[1] -ne 0x50 -or
        $bytes[2] -ne 0x4E -or
        $bytes[3] -ne 0x47 -or
        $bytes[4] -ne 0x0D -or
        $bytes[5] -ne 0x0A -or
        $bytes[6] -ne 0x1A -or
        $bytes[7] -ne 0x0A) {
        throw "Icon master is not a valid PNG: $Path"
    }
}

'@

$text = $text.Substring(0, $start) + $replacement + $text.Substring($end)

$stageRegex = [regex]::new(
    '(?ms)^    \$remote = "assets/icons/concepts/\$fileName"\r?\n' +
    '    \$conceptPath = Join-Path \$IconConceptDir \$fileName\r?\n\r?\n' +
    '    Get-CompletionistGitHubBinary -RemotePath \$remote -Destination \$conceptPath'
)

if ($stageRegex.Matches($text).Count -ne 1) {
    throw 'Expected exactly one v0.10.0 icon download staging block.'
}

$stageReplacement = @'
    $sourceConceptPath = Join-Path $IconSourceDir $fileName
    $conceptPath = Join-Path $IconConceptDir $fileName

    Assert-CompletionistPng -Path $sourceConceptPath
    Copy-Item $sourceConceptPath $conceptPath -Force
    Assert-CompletionistPng -Path $conceptPath
'@

$text = $stageRegex.Replace(
    $text,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $stageReplacement.TrimEnd() },
    1
)

# Keep the already field-proven internal V100 Lua symbol names to minimise risk.
# Only user-visible version strings/log prefixes move to v0.10.1.
$text = $text.Replace('v0.10.0', 'v0.10.1')
$text = $text.Replace(
    "- v0.10.1 downloads ALL user-authored concept PNG masters from feat/completionist-icon-system",
    "- v0.10.1 uses bundled/local user-authored concept PNG masters with no GitHub/network dependency"
)

# The v0.10.0 seed validated HUD_ICON_CAPS before $hudHelper was injected into
# $hudText. Move the assertion to the post-injection point so it validates the
# final generated HUD script instead of the untouched source script.
$earlyHudValidation = @'
if (-not $hudText.Contains('HUD_ICON_CAPS')) {
    throw 'v0.10.1 HUD icon capability probe is missing.'
}

'@

if (-not $text.Contains($earlyHudValidation)) {
    throw 'Could not locate the early v0.10.1 HUD_ICON_CAPS validation block.'
}
$text = $text.Replace($earlyHudValidation, '')

$hudHookAnchor = @'
$hudText = $setupTailRegex.Replace(
    $hudText,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $setupTailReplacement },
    1
)

'@

if (-not $text.Contains($hudHookAnchor)) {
    throw 'Could not locate the post-HUD-hook validation anchor.'
}

$postHudValidation = @'
$hudText = $setupTailRegex.Replace(
    $hudText,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $setupTailReplacement },
    1
)

if (-not $hudText.Contains('HUD_ICON_CAPS')) {
    throw 'v0.10.1 HUD icon capability probe is missing after HUD injection.'
}

if (-not $hudText.Contains('[CompletionistMap v0.10.1] HUD_HOOK installed=true')) {
    throw 'v0.10.1 HUD update hook is missing after HUD injection.'
}

'@

$text = $text.Replace($hudHookAnchor, $postHudValidation)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($installerPath, $text, $utf8NoBom)

Write-Host "Patched: $installerPath"
Write-Host "Icon source resolution: bundled package assets first, cloned repo assets second."
Write-Host "No gh/token/private raw URL is required by the v0.10.1 installer."
Write-Host "HUD capability validation now runs after HUD helper injection."
