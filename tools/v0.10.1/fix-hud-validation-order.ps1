$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installerPath = Join-Path $scriptDir 'install.ps1'

if (-not (Test-Path $installerPath)) {
    throw "Missing installer: $installerPath"
}

$text = [IO.File]::ReadAllText($installerPath)

$earlyValidation = @'
if (-not $hudText.Contains('HUD_ICON_CAPS')) {
    throw 'v0.10.1 HUD icon capability probe is missing.'
}

'@

$earlyCount = ([regex]::Matches(
    $text,
    [regex]::Escape($earlyValidation)
)).Count

if ($earlyCount -ne 1) {
    throw "Expected exactly one early HUD_ICON_CAPS validation block, found $earlyCount."
}

$text = $text.Replace($earlyValidation, '')

$anchor = @'
$hudText = $setupTailRegex.Replace(
    $hudText,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $setupTailReplacement },
    1
)

'@

$anchorCount = ([regex]::Matches(
    $text,
    [regex]::Escape($anchor)
)).Count

if ($anchorCount -ne 1) {
    throw "Expected exactly one post-HUD-hook anchor, found $anchorCount."
}

$postValidation = @'
$hudText = $setupTailRegex.Replace(
    $hudText,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $setupTailReplacement },
    1
)

# Validate HUD instrumentation only after the helper and Update hook have been
# injected into $hudText. The previous v0.10.1 seed checked this too early and
# failed even though HUD_ICON_CAPS was present in $hudHelper.
if (-not $hudText.Contains('HUD_ICON_CAPS')) {
    throw 'v0.10.1 HUD icon capability probe is missing after HUD injection.'
}

if (-not $hudText.Contains('[CompletionistMap v0.10.1] HUD_HOOK installed=true')) {
    throw 'v0.10.1 HUD update hook is missing after HUD injection.'
}

'@

$text = $text.Replace($anchor, $postValidation)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($installerPath, $text, $utf8NoBom)

Write-Host "Fixed HUD validation order: $installerPath"
Write-Host 'HUD_ICON_CAPS is now validated after the HUD helper is injected.'
Write-Host 'HUD_HOOK is also validated at the same post-injection point.'
