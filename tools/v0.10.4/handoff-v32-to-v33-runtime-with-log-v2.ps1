param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$delegate = Join-Path $PSScriptRoot 'handoff-v32-to-v33-runtime-with-log.ps1'
if (-not (Test-Path -LiteralPath $delegate -PathType Leaf)) {
    throw "Missing delegated handoff helper: $delegate"
}

# Git for Windows can emit advisory CRLF messages on stderr while `git diff
# --name-status` still succeeds and prints valid status records on stdout. The
# delegated helper intentionally merges stderr/stdout for its self-log, so those
# advisory lines previously looked like malformed status rows. Filter only these
# known advisory lines; preserve every other Git line and the real exit code.
function global:git {
    $captured = @(& git.exe @args 2>&1)
    $code = $LASTEXITCODE
    foreach ($item in $captured) {
        $text = $item.ToString()
        if ($text -match '^warning: in the working copy of ' -and
            $text -match 'LF will be replaced by CRLF the next time Git touches it$') {
            continue
        }
        $item
    }
    $global:LASTEXITCODE = $code
}

try {
    & $delegate -GameRoot $GameRoot
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Remove-Item Function:\git -ErrorAction SilentlyContinue
}
