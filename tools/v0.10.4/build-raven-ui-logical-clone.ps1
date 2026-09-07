param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') {
    throw "Expected feat/v0.10.4-all-ravens, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before building the offline Raven UI logical clone.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$script = Join-Path $PSScriptRoot 'build-raven-ui-logical-clone.py'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Missing builder: $script"
}
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

# dddd8db shipped two malformed dictionary comprehensions in the Python builder.
# Repair those exact lines locally, syntax-check the result, then commit/push only
# the corrected builder before running the offline build. This block is idempotent
# and becomes a no-op once the repair commit has reached the branch.
$builderText = [System.IO.File]::ReadAllText($script)
$builderFixed = $builderText.Replace(
    'original_by_kind = {c["kind"]: raw[c["start"]:c["end"] for c in chunks if c["kind"] != 12}',
    'original_by_kind = {c["kind"]: raw[c["start"]:c["end"]] for c in chunks if c["kind"] != 12}'
).Replace(
    'candidate_by_kind = {c["kind"]: candidate[c["start"]:c["end"] for c in reparsed if c["kind"] != 12}',
    'candidate_by_kind = {c["kind"]: candidate[c["start"]:c["end"]] for c in reparsed if c["kind"] != 12}'
)
$builderRepaired = $builderFixed -ne $builderText
if ($builderRepaired) {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($script, $builderFixed, $utf8NoBom)
}

& $python.Source -m py_compile $script
$compileExit = $LASTEXITCODE
Remove-Item -LiteralPath (Join-Path $PSScriptRoot '__pycache__') -Recurse -Force -ErrorAction SilentlyContinue
if ($compileExit -ne 0) {
    throw 'Raven UI logical clone builder still fails Python syntax validation.'
}

if ($builderRepaired) {
    Push-Location $repo
    try {
        $builderRel = 'tools/v0.10.4/build-raven-ui-logical-clone.py'
        git add -- $builderRel
        if ($LASTEXITCODE -ne 0) { throw 'git add of repaired builder failed.' }
        git diff --cached --check -- $builderRel
        if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check of repaired builder failed.' }
        git commit -m 'Fix Raven UI logical clone builder syntax' -- $builderRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit of repaired builder failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) {
            throw "git push failed; the syntax-fix commit remains local on '$branch'."
        }
        Write-Host "Pushed Raven UI builder syntax fix to $Remote/$branch"
    }
    finally {
        Pop-Location
    }
}

$outRel = 'archive/field-logs/completionist-v104-raven-ui-logical-clone.json'
$out = Join-Path $repo ($outRel -replace '/', '\')
$work = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.4\raven-ui-logical-clone'
New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent), $work | Out-Null

& $python.Source $script --game-root $GameRoot --work-dir $work --output $out
if ($LASTEXITCODE -ne 0) {
    throw 'Offline Raven UI logical clone build failed.'
}
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) {
    throw 'Raven UI logical clone validation report was not produced.'
}
foreach ($candidate in @((Join-Path $work 'r_ui.wad'), (Join-Path $work 'wad_r_ui.dcb'))) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Expected offline candidate missing: $candidate"
    }
}

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }

    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Raven UI logical clone report unchanged; nothing to commit.'
    }
    else {
        git commit -m 'Archive Raven UI logical clone validation' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) {
            throw "git push failed; the validation commit remains local on '$branch'."
        }
        Write-Host "Pushed Raven UI logical clone validation to $Remote/$branch"
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Offline Raven UI logical clone build complete.'
Write-Host "Candidate directory: $work"
Write-Host 'Nothing was installed into God of War.'
Write-Host 'At this gate the dedicated Raven identity intentionally still shares the stock Dock prototype/artwork.'
