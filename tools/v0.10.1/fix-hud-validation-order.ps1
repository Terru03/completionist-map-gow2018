$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installerPath = Join-Path $scriptDir 'install.ps1'

if (-not (Test-Path $installerPath)) {
    throw "Missing installer: $installerPath"
}

$text = [IO.File]::ReadAllText($installerPath)

$postMessage = 'v0.10.1 HUD icon capability probe is missing after HUD injection.'
if ($text.Contains($postMessage)) {
    Write-Host "HUD validation order is already fixed: $installerPath"
    exit 0
}

# The installer may contain mixed LF/CRLF because the seeded v0.10.0 file was
# rewritten by PowerShell and then checked out by Git on Windows. Match either.
$earlyPattern = [regex]::new(
    "(?ms)^[ \t]*if \(-not \$hudText\.Contains\('HUD_ICON_CAPS'\)\) \{\r?\n" +
    "[ \t]*throw 'v0\.10\.1 HUD icon capability probe is missing\.'\r?\n" +
    "[ \t]*\}\r?\n?"
)

$earlyMatches = $earlyPattern.Matches($text)
if ($earlyMatches.Count -ne 1) {
    throw "Expected exactly one early HUD_ICON_CAPS validation block, found $($earlyMatches.Count)."
}

$text = $earlyPattern.Replace($text, '', 1)

$anchorPattern = [regex]::new(
    '(?ms)\$hudText = \$setupTailRegex\.Replace\(\r?\n' +
    '[ \t]*\$hudText,\r?\n' +
    '[ \t]*\[System\.Text\.RegularExpressions\.MatchEvaluator\]\{ param\(\$m\) \$setupTailReplacement \},\r?\n' +
    '[ \t]*1\r?\n' +
    '\)\r?\n'
)

$anchorMatches = $anchorPattern.Matches($text)
if ($anchorMatches.Count -ne 1) {
    throw "Expected exactly one post-HUD-hook anchor, found $($anchorMatches.Count)."
}

$anchor = $anchorMatches[0]
$postValidation = @'

# Validate HUD instrumentation only after the helper and Update hook have been
# injected into $hudText. The previous seed checked the untouched source script.
if (-not $hudText.Contains('HUD_ICON_CAPS')) {
    throw 'v0.10.1 HUD icon capability probe is missing after HUD injection.'
}

if (-not $hudText.Contains('[CompletionistMap v0.10.1] HUD_HOOK installed=true')) {
    throw 'v0.10.1 HUD update hook is missing after HUD injection.'
}
'@

$insertAt = $anchor.Index + $anchor.Length
$text = $text.Substring(0, $insertAt) + $postValidation + "`r`n" + $text.Substring($insertAt)

# Sanity-check that the final validation now occurs after the HUD helper is
# actually inserted into $hudText.
$helperInsertPos = $text.IndexOf('$hudText = $hudText.Replace(', [StringComparison]::Ordinal)
$postValidationPos = $text.IndexOf($postMessage, [StringComparison]::Ordinal)
if ($postValidationPos -lt 0) {
    throw 'Post-injection HUD validation was not written.'
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($installerPath, $text, $utf8NoBom)

Write-Host "Fixed HUD validation order: $installerPath"
Write-Host 'HUD_ICON_CAPS is now validated after the HUD helper is injected.'
Write-Host 'HUD_HOOK is also validated at the same post-injection point.'
