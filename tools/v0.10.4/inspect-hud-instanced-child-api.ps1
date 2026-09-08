param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}

$game = [IO.Path]::GetFullPath($GameRoot)
$sourceRoot = Join-Path $game 'mods\lua\gameart\ui\scripts'
if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
    throw "Extracted UI Lua source root not found: $sourceRoot"
}

$patterns = [ordered]@{
    'GetInstancedChildObject' = 'GetInstancedChildObject'
    'GetChildSubObject'       = 'GetChildSubObject'
    'SetMaterialSwap'         = 'SetMaterialSwap'
    'UI.WorldUIRender'        = 'UI.WorldUIRender'
    'UI.SendEvent'            = 'UI.SendEvent'
}

$files = @(Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Filter '*.lua' | Sort-Object FullName)
if ($files.Count -eq 0) {
    throw "No Lua files found under $sourceRoot"
}

$counts = [ordered]@{}
foreach ($key in $patterns.Keys) { $counts[$key] = 0 }
$blocks = New-Object System.Collections.Generic.List[string]
$contextRadius = 4

foreach ($file in $files) {
    $lines = [IO.File]::ReadAllLines($file.FullName)
    $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart('\')

    for ($i = 0; $i -lt $lines.Length; $i++) {
        foreach ($key in $patterns.Keys) {
            $needle = [string]$patterns[$key]
            if ($lines[$i].IndexOf($needle, [StringComparison]::Ordinal) -lt 0) { continue }

            $counts[$key] = [int]$counts[$key] + 1
            $blocks.Add('')
            $blocks.Add(('=== {0} :: {1} :: line {2} ===' -f $relative, $key, ($i + 1)))
            $start = [Math]::Max(0, $i - $contextRadius)
            $end = [Math]::Min($lines.Length - 1, $i + $contextRadius)
            for ($j = $start; $j -le $end; $j++) {
                $mark = if ($j -eq $i) { '>' } else { ' ' }
                $clean = ([string]$lines[$j]).TrimEnd()
                $blocks.Add(('{0} {1,5}: {2}' -f $mark, ($j + 1), $clean))
            }
        }
    }
}

$reportRel = 'archive/field-logs/completionist-v104-hud-instanced-child-api.txt'
$report = Join-Path $repo ($reportRel -replace '/', '\')
$utf8 = New-Object Text.UTF8Encoding($false)

$header = New-Object System.Collections.Generic.List[string]
$header.Add('Completionist Map v0.10.4 HUD instanced-child/API source context')
$header.Add(('Generated UTC: ' + [DateTime]::UtcNow.ToString('o')))
$header.Add(('Source root: ' + $sourceRoot))
$header.Add(('Lua files scanned: ' + $files.Count))
$header.Add('Game files written: false')
$header.Add('')
$header.Add('MATCH COUNTS')
foreach ($key in $patterns.Keys) {
    $header.Add(('{0}: {1}' -f $key, $counts[$key]))
}
$header.Add('')
$header.Add('PURPOSE')
$header.Add('Resolve real engine-Lua call signatures and ownership context before probing renderer-owned compass instances. This report is read-only and does not alter HUD, map, saves, progression, or marker state.')

New-Item -ItemType Directory -Force -Path (Split-Path $report -Parent) | Out-Null
[IO.File]::WriteAllLines($report, @($header + $blocks), $utf8)
Write-Host "Saved: $report"
foreach ($key in $patterns.Keys) {
    Write-Host ("{0}: {1}" -f $key, $counts[$key])
}
Write-Host 'No God of War files were modified.'

Push-Location $repo
try {
    git add -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for HUD API source report.' }
    git diff --cached --check -- $reportRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed for HUD API source report.' }

    git diff --cached --quiet -- $reportRel
    if ($LASTEXITCODE -ne 0) {
        git commit -m 'Archive HUD instanced-child API context' -- $reportRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for HUD API source report.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) {
            Write-Warning 'HUD API source report was committed locally but push failed.'
        }
    }
    else {
        Write-Host 'HUD API source report is unchanged; nothing to commit.'
    }
}
finally {
    Pop-Location
}
