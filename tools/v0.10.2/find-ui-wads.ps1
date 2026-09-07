param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'

$repo = (& git rev-parse --show-toplevel).Trim()
if (-not $repo) { throw 'Run this script from inside the Completionist Map Git repository.' }

$branch = (& git branch --show-current).Trim()
if (-not $branch) { throw 'Detached HEAD is not supported.' }

$wadRoot = Join-Path $GameRoot 'exec\wad\pc_le'
if (-not (Test-Path $wadRoot)) { throw "WAD root not found: $wadRoot" }

$outDir = Join-Path $repo 'archive\field-logs'
$out = Join-Path $outDir 'completionist-v102-ui-wads.txt'
New-Item -ItemType Directory -Force $outDir | Out-Null

$wads = Get-ChildItem -LiteralPath $wadRoot -Recurse -File -Filter '*.wad' -ErrorAction Stop |
    Sort-Object Name, FullName

# Match only the WAD filename, never the absolute Steam path. The previous inventory
# accidentally matched the "steamapps" directory because it contains the letters "map".
$strongRegex = '(?i)(ui|hud|menu|shell|map|icon|marker|compass|frontend|interface)'
$globalRegex = '(?i)(global|common|root|shared|system|boot|generic)'

$strong = @($wads | Where-Object { $_.Name -match $strongRegex })
$global = @($wads | Where-Object { $_.Name -match $globalRegex })

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('=== Completionist Map v0.10.2 UI WAD candidate scan ===')
$lines.Add("Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')")
$lines.Add("GameRoot: $GameRoot")
$lines.Add("Branch: $branch")
$lines.Add("Total WADs: $($wads.Count)")
$lines.Add('')

$lines.Add('=== strong UI / HUD / map filename matches ===')
if ($strong.Count -eq 0) {
    $lines.Add('<none>')
} else {
    foreach ($file in $strong) {
        $relative = $file.FullName.Substring($GameRoot.Length).TrimStart('\')
        $lines.Add(('{0,10:N2} MiB  {1}' -f ($file.Length / 1MB), $relative))
    }
}
$lines.Add('')

$lines.Add('=== global / shared filename matches ===')
if ($global.Count -eq 0) {
    $lines.Add('<none>')
} else {
    foreach ($file in $global) {
        $relative = $file.FullName.Substring($GameRoot.Length).TrimStart('\')
        $lines.Add(('{0,10:N2} MiB  {1}' -f ($file.Length / 1MB), $relative))
    }
}
$lines.Add('')

$lines.Add('=== exact short-name candidates ===')
$exactPatterns = @(
    'ui.wad', 'hud.wad', 'map.wad', 'menu.wad', 'shell.wad',
    'global.wad', 'root.wad', 'common.wad', 'interface.wad'
)
foreach ($pattern in $exactPatterns) {
    $matches = @($wads | Where-Object { $_.Name -ieq $pattern })
    if ($matches.Count -eq 0) {
        $lines.Add("$pattern`t<not present>")
    } else {
        foreach ($file in $matches) {
            $relative = $file.FullName.Substring($GameRoot.Length).TrimStart('\')
            $lines.Add("$pattern`t$relative")
        }
    }
}
$lines.Add('')

$lines.Add('=== notes ===')
$lines.Add('This scan is filename-only and read-only.')
$lines.Add('It intentionally avoids matching the absolute Steam path.')
$lines.Add('The next step is to export DDS textures only from the strongest shared UI/map WAD candidate using GOWTool v0.1.3-alpha (PC 2018).')

$lines | Set-Content -LiteralPath $out -Encoding UTF8
Write-Host "Saved candidate scan: $out"
Write-Host "Strong UI/map matches: $($strong.Count)"
Write-Host "Global/shared matches: $($global.Count)"

$relativeOut = 'archive/field-logs/completionist-v102-ui-wads.txt'
& git add -- $relativeOut
if ($LASTEXITCODE -ne 0) { throw 'git add failed for the UI WAD scan.' }

& git diff --cached --quiet -- $relativeOut
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Candidate scan is unchanged. Nothing to commit.'
    exit 0
}

& git commit -m 'Archive v0.10.2 UI WAD candidate scan' -- $relativeOut
if ($LASTEXITCODE -ne 0) { throw 'git commit failed for the UI WAD scan.' }

& git push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw "git push failed. The scan commit exists locally on '$branch'." }

Write-Host "Pushed candidate scan to $Remote/$branch"
