param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$ToolPath = "$env:LOCALAPPDATA\CompletionistMap\tools\GOWTool-v0.1.3-alpha\GOWTool.exe",
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'

$repo = (& git rev-parse --show-toplevel).Trim()
if (-not $repo) {
    throw 'Run this script from inside the Completionist Map Git repository.'
}

$branch = (& git branch --show-current).Trim()
if (-not $branch) {
    throw 'Detached HEAD is not supported.'
}

if (-not (Test-Path -LiteralPath $GameRoot)) {
    throw "God of War root not found: $GameRoot"
}
if (-not (Test-Path -LiteralPath $ToolPath)) {
    throw "GOWTool not found: $ToolPath. Run prepare-gowtool.ps1 first."
}

$wad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
if (-not (Test-Path -LiteralPath $wad)) {
    throw "r_ui.wad not found: $wad"
}

$workRoot = Join-Path $env:LOCALAPPDATA 'CompletionistMap\work\v0.10.2'
$outDir = Join-Path $workRoot 'r_ui-dds'
Remove-Item -LiteralPath $outDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

Write-Host 'Exporting DDS textures referenced by r_ui.wad...'
Write-Host "WAD: $wad"
Write-Host "Output: $outDir"

$toolOutput = & $ToolPath wad -p $wad -o $outDir -t -d 2>&1
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    $toolOutput | ForEach-Object { Write-Host $_ }
    throw "GOWTool r_ui texture export failed with exit code $exitCode."
}

$ddsFiles = @(Get-ChildItem -LiteralPath $outDir -File -Filter '*.dds' -ErrorAction SilentlyContinue | Sort-Object Name)
if ($ddsFiles.Count -eq 0) {
    throw 'GOWTool completed but no DDS files were exported from r_ui.wad.'
}

function Get-DdsDimensions {
    param([Parameter(Mandatory=$true)][string]$Path)

    $fs = [System.IO.File]::OpenRead($Path)
    try {
        if ($fs.Length -lt 20) {
            return $null
        }
        $br = New-Object System.IO.BinaryReader($fs)
        $magic = $br.ReadUInt32()
        if ($magic -ne 0x20534444) {
            return $null
        }
        $null = $br.ReadUInt32() # DDS_HEADER size
        $null = $br.ReadUInt32() # flags
        $height = $br.ReadUInt32()
        $width = $br.ReadUInt32()
        return [pscustomobject]@{ Width = $width; Height = $height }
    }
    finally {
        $fs.Dispose()
    }
}

$records = foreach ($file in $ddsFiles) {
    $dims = Get-DdsDimensions -Path $file.FullName
    [pscustomobject]@{
        Name = $file.Name
        Length = $file.Length
        Width = if ($dims) { [int]$dims.Width } else { 0 }
        Height = if ($dims) { [int]$dims.Height } else { 0 }
    }
}

$keywords = '(?i)(map|marker|icon|compass|dock|boat|poi|waypoint|player|kratos|quest|vendor|travel|valkyr|raven|chest|runic|nornir|objective|cursor)'
$interesting = @($records | Where-Object { $_.Name -match $keywords })

$dimensionGroups = $records |
    Group-Object { "{0}x{1}" -f $_.Width, $_.Height } |
    Sort-Object Count -Descending, Name

$smallUi = @($records | Where-Object {
    $_.Width -gt 0 -and $_.Height -gt 0 -and
    $_.Width -le 512 -and $_.Height -le 512
})

$reportDir = Join-Path $repo 'archive\field-logs'
$report = Join-Path $reportDir 'completionist-v102-r-ui-textures.txt'
New-Item -ItemType Directory -Force $reportDir | Out-Null

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('=== Completionist Map v0.10.2 r_ui texture inventory ===')
$lines.Add("Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')")
$lines.Add("Branch: $branch")
$lines.Add("WAD: $wad")
$lines.Add("GOWTool: $ToolPath")
$lines.Add("Local DDS output: $outDir")
$lines.Add("GOWTool exit: $exitCode")
$lines.Add("DDS textures exported: $($records.Count)")
$lines.Add('')

$lines.Add('=== GOWTool output ===')
foreach ($entry in $toolOutput) {
    $lines.Add([string]$entry)
}
$lines.Add('')

$lines.Add('=== keyword matches ===')
if ($interesting.Count -eq 0) {
    $lines.Add('<none>')
}
else {
    foreach ($r in $interesting) {
        $lines.Add(('{0,5}x{1,-5}  {2,10:N2} KiB  {3}' -f $r.Width, $r.Height, ($r.Length / 1KB), $r.Name))
    }
}
$lines.Add('')

$lines.Add('=== dimension histogram ===')
foreach ($g in $dimensionGroups) {
    $lines.Add(('{0,12}  {1,5}' -f $g.Name, $g.Count))
}
$lines.Add('')

$lines.Add('=== small UI-sized textures (<=512x512) ===')
foreach ($r in ($smallUi | Sort-Object Width, Height, Name)) {
    $lines.Add(('{0,5}x{1,-5}  {2,10:N2} KiB  {3}' -f $r.Width, $r.Height, ($r.Length / 1KB), $r.Name))
}
$lines.Add('')

$lines.Add('=== all exported DDS textures ===')
foreach ($r in $records) {
    $lines.Add(('{0,5}x{1,-5}  {2,10:N2} KiB  {3}' -f $r.Width, $r.Height, ($r.Length / 1KB), $r.Name))
}
$lines.Add('')
$lines.Add('=== notes ===')
$lines.Add('DDS files remain under LocalAppData and are not added to Git.')
$lines.Add('This script does not modify God of War game files.')
$lines.Add('The report is intended to identify candidate map/DockPoint/UI texture hashes for the next replacement test.')

$lines | Set-Content -LiteralPath $report -Encoding UTF8
Write-Host "Saved report: $report"
Write-Host "DDS textures: $($records.Count)"
Write-Host "Keyword matches: $($interesting.Count)"
Write-Host "Small UI-sized textures: $($smallUi.Count)"

$relativeReport = 'archive/field-logs/completionist-v102-r-ui-textures.txt'
& git add -- $relativeReport
if ($LASTEXITCODE -ne 0) {
    throw 'git add failed for the r_ui texture inventory.'
}

& git diff --cached --quiet -- $relativeReport
$hasChanges = $LASTEXITCODE -ne 0
if (-not $hasChanges) {
    Write-Host 'Report is unchanged. Nothing to commit.'
    exit 0
}

& git commit -m 'Archive v0.10.2 r_ui texture inventory' -- $relativeReport
if ($LASTEXITCODE -ne 0) {
    throw 'git commit failed for the r_ui texture inventory.'
}

& git push $Remote $branch
if ($LASTEXITCODE -ne 0) {
    throw "git push failed. The inventory commit exists locally on '$branch'."
}

Write-Host "Pushed r_ui texture inventory to $Remote/$branch"
