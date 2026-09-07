param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'

$repo = (& git rev-parse --show-toplevel).Trim()
if (-not $repo) { throw 'Run this script from inside the Completionist Map Git repository.' }
$branch = (& git branch --show-current).Trim()
if (-not $branch) { throw 'Detached HEAD is not supported.' }
if (-not (Test-Path -LiteralPath $GameRoot)) { throw "God of War root not found: $GameRoot" }

$targetHashes = @{
    DockDiffuse  = [UInt64]::Parse('982BF904AB84F2CC', [Globalization.NumberStyles]::HexNumber)
    DockEmissive = [UInt64]::Parse('FCC664130951154C', [Globalization.NumberStyles]::HexNumber)
}
$targetHashList = [UInt64[]]@(
    [UInt64]$targetHashes.DockDiffuse,
    [UInt64]$targetHashes.DockEmissive
)

function Read-TexpackHeader {
    param([Parameter(Mandatory=$true)][string]$Path)

    $fs = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $br = New-Object IO.BinaryReader($fs)
        if ($fs.Length -lt 56) { throw "Texpack is too small: $Path" }
        $fs.Position = 0x20
        $texSectionOff = $br.ReadUInt32()
        $blocksCount = $br.ReadUInt32()
        $blocksInfoOff = $br.ReadUInt32()
        $texCount = $br.ReadUInt32()
        $marker = $br.ReadUInt64()
        [pscustomobject]@{
            TexSectionOff = $texSectionOff
            BlocksCount = $blocksCount
            BlocksInfoOff = $blocksInfoOff
            TexCount = $texCount
            Marker = $marker
            Length = $fs.Length
        }
    }
    finally {
        $fs.Dispose()
    }
}

function Find-TexpackEntries {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][UInt64[]]$Hashes
    )

    $wanted = @{}
    foreach ($h in $Hashes) { $wanted[[UInt64]$h] = $true }

    $fs = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $br = New-Object IO.BinaryReader($fs)
        if ($fs.Length -lt 56) { return @() }
        $fs.Position = 0x2C
        $texCount = $br.ReadUInt32()
        $fs.Position = 0x38

        # Plain PowerShell array is deliberate here. Windows PowerShell 5.1 can
        # throw "Argument types do not match" when a generic List[object] is
        # wrapped/returned through @(...).
        $found = @()
        for ($i = 0; $i -lt $texCount; $i++) {
            if (($fs.Position + 24) -gt $fs.Length) { break }
            $fileHash = [UInt64]$br.ReadUInt64()
            $userHash = [UInt64]$br.ReadUInt64()
            $blockInfoOff = $br.ReadUInt64()
            if ($wanted.ContainsKey($fileHash)) {
                $found += [pscustomobject]@{
                    Index = $i
                    FileHash = $fileHash
                    UserHash = $userHash
                    BlockInfoOff = $blockInfoOff
                }
            }
        }
        return $found
    }
    finally {
        $fs.Dispose()
    }
}

function Hex64([UInt64]$Value) { return ('{0:X16}' -f $Value) }

$bootPath = Join-Path $GameRoot 'exec\boot-options.json'
$bootBackup = "$bootPath.completionist-v102-before-dock-raven.bak"
$patchPath = Join-Path $GameRoot 'exec\patch\pc_le\completionist_v102_dock_raven.texpack'
$patchToc = "$patchPath.toc"
$wadTexRoot = Join-Path $GameRoot 'exec\wad\pc_le'

foreach ($required in @($bootPath, $patchPath, $patchToc, $wadTexRoot)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required path not found: $required" }
}

$bootRaw = Get-Content -LiteralPath $bootPath -Raw
$boot = $bootRaw | ConvertFrom-Json
$patchEntries = @($boot.'patch-texpacks')
$expectedBootEntry = '../../patch/pc_le/completionist_v102_dock_raven'

$patchHeader = Read-TexpackHeader -Path $patchPath
$patchFound = @(Find-TexpackEntries -Path $patchPath -Hashes $targetHashList)

# Also use a normal PowerShell array here for PS 5.1 compatibility.
$baseMatches = @()
$basePacks = @(Get-ChildItem -LiteralPath $wadTexRoot -Recurse -File -Filter '*.texpack' -ErrorAction Stop | Sort-Object FullName)
foreach ($pack in $basePacks) {
    $matches = @(Find-TexpackEntries -Path $pack.FullName -Hashes $targetHashList)
    foreach ($m in $matches) {
        $baseMatches += [pscustomobject]@{
            Pack = $pack.FullName
            Index = $m.Index
            FileHash = $m.FileHash
            UserHash = $m.UserHash
            BlockInfoOff = $m.BlockInfoOff
        }
    }
}

$reportDir = Join-Path $repo 'archive\field-logs'
$report = Join-Path $reportDir 'completionist-v102-dock-raven-verify.txt'
New-Item -ItemType Directory -Force $reportDir | Out-Null

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('=== Completionist Map v0.10.2 DockPoint Raven patch verification ===')
$lines.Add("Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')")
$lines.Add("Branch: $branch")
$lines.Add("GameRoot: $GameRoot")
$lines.Add('')
$lines.Add('=== boot-options.json ===')
$lines.Add("Expected entry present: $($patchEntries -contains $expectedBootEntry)")
$lines.Add("Expected entry: $expectedBootEntry")
$lines.Add("patch-texpacks count: $($patchEntries.Count)")
foreach ($entry in $patchEntries) { $lines.Add("  $entry") }
$lines.Add("Backup exists: $(Test-Path -LiteralPath $bootBackup)")
$lines.Add('')
$lines.Add('=== patch files ===')
$lines.Add("Texpack: $patchPath")
$lines.Add("Texpack bytes: $((Get-Item -LiteralPath $patchPath).Length)")
$lines.Add("Texpack SHA256: $((Get-FileHash -LiteralPath $patchPath -Algorithm SHA256).Hash)")
$lines.Add("TOC: $patchToc")
$lines.Add("TOC bytes: $((Get-Item -LiteralPath $patchToc).Length)")
$lines.Add('')
$lines.Add('=== patch texpack header ===')
$lines.Add("TexSectionOff: 0x$('{0:X}' -f $patchHeader.TexSectionOff)")
$lines.Add("BlocksCount: $($patchHeader.BlocksCount)")
$lines.Add("BlocksInfoOff: 0x$('{0:X}' -f $patchHeader.BlocksInfoOff)")
$lines.Add("TexCount: $($patchHeader.TexCount)")
$lines.Add("Marker: 0x$('{0:X}' -f $patchHeader.Marker)")
$lines.Add('')
$lines.Add('=== target hashes expected ===')
foreach ($pair in $targetHashes.GetEnumerator() | Sort-Object Name) {
    $lines.Add("$($pair.Name): $(Hex64 $pair.Value)")
}
$lines.Add('')
$lines.Add('=== target entries inside patch texpack ===')
if ($patchFound.Count -eq 0) {
    $lines.Add('<none>')
}
else {
    foreach ($m in $patchFound) {
        $lines.Add("index=$($m.Index) fileHash=$(Hex64 $m.FileHash) userHash=$(Hex64 $m.UserHash) blockInfoOff=0x$('{0:X}' -f $m.BlockInfoOff)")
    }
}
$lines.Add('')
$lines.Add('=== matching target entries in stock texpack set ===')
if ($baseMatches.Count -eq 0) {
    $lines.Add('<none>')
}
else {
    foreach ($m in $baseMatches | Sort-Object Pack, FileHash) {
        $rel = $m.Pack.Substring($GameRoot.Length).TrimStart('\')
        $lines.Add("$rel | index=$($m.Index) fileHash=$(Hex64 $m.FileHash) userHash=$(Hex64 $m.UserHash) blockInfoOff=0x$('{0:X}' -f $m.BlockInfoOff)")
    }
}
$lines.Add('')
$lines.Add('=== patch vs stock user-hash comparison ===')
foreach ($pair in $targetHashes.GetEnumerator() | Sort-Object Name) {
    $h = [UInt64]$pair.Value
    $p = @($patchFound | Where-Object FileHash -eq $h)
    $b = @($baseMatches | Where-Object FileHash -eq $h)
    if ($p.Count -eq 0) {
        $lines.Add("$($pair.Name): FAIL - target file hash absent from patch texpack")
        continue
    }
    if ($b.Count -eq 0) {
        $lines.Add("$($pair.Name): FAIL - target file hash absent from stock texpack set")
        continue
    }
    $stockUsers = @($b | ForEach-Object { Hex64 $_.UserHash } | Sort-Object -Unique)
    $patchUsers = @($p | ForEach-Object { Hex64 $_.UserHash } | Sort-Object -Unique)
    $same = @($patchUsers | Where-Object { $stockUsers -contains $_ }).Count -gt 0
    $lines.Add("$($pair.Name): userHashMatch=$same patch=$($patchUsers -join ',') stock=$($stockUsers -join ',')")
}
$lines.Add('')
$lines.Add('=== conclusion hints ===')
$lines.Add('If the boot entry is present and both fileHash/userHash pairs match stock, the pack itself is structurally targeting the correct textures and the next suspect is patch loading/precedence.')
$lines.Add('If file hashes are absent or user hashes differ, rebuild the patch before any further runtime test.')
$lines.Add('No game files are modified by this verification script.')

$lines | Set-Content -LiteralPath $report -Encoding UTF8
Write-Host "Saved verification report: $report"
Write-Host "Patch target entries found: $($patchFound.Count)"
Write-Host "Stock target entries found: $($baseMatches.Count)"
Write-Host "Boot entry present: $($patchEntries -contains $expectedBootEntry)"

$relativeReport = 'archive/field-logs/completionist-v102-dock-raven-verify.txt'
& git add -- $relativeReport
if ($LASTEXITCODE -ne 0) { throw 'git add failed for the patch verification report.' }
& git diff --cached --quiet -- $relativeReport
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Verification report is unchanged. Nothing to commit.'
    exit 0
}
& git commit -m 'Archive v0.10.2 texture patch verification' -- $relativeReport
if ($LASTEXITCODE -ne 0) { throw 'git commit failed for the patch verification report.' }
& git push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw "git push failed. The verification commit exists locally on '$branch'." }
Write-Host "Pushed verification report to $Remote/$branch"
