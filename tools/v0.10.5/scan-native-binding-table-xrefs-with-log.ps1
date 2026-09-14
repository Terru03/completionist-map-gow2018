param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/source-scans/native-binding-table-xrefs-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$xrefPath = Join-Path $logDir 'table-xrefs.txt'
$published = $false
$transcriptStarted = $false
$tempDisassembly = $null

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Write-Result([string]$Result) {
    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
        'scan_only=true'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8
}

function Publish-Scan([string]$Result) {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    Write-Result $Result
    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add of scan directory failed.' }
    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 0) { return }
    if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged scan changes.' }
    & git commit -m "Archive native binding table xref scan $stamp" -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git commit of scan directory failed.' }
    & git push origin "HEAD:$expectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'git push of scan directory failed.' }
}

function Find-Objdump {
    $cmd = Get-Command objdump.exe -ErrorAction SilentlyContinue
    if ($null -ne $cmd) { return $cmd.Source }
    $cmd = Get-Command objdump -ErrorAction SilentlyContinue
    if ($null -ne $cmd) { return $cmd.Source }
    $candidates = @(
        'C:\Program Files\Git\usr\bin\objdump.exe',
        'C:\Program Files\Git\mingw64\bin\objdump.exe',
        'C:\Program Files (x86)\Git\usr\bin\objdump.exe',
        'C:\Program Files (x86)\Git\mingw64\bin\objdump.exe'
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    throw 'GNU objdump.exe not found.'
}

function Read-PeLayout([string]$ExePath) {
    $fs = [IO.File]::Open($ExePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $br = New-Object IO.BinaryReader($fs)
        if ($br.ReadUInt16() -ne 0x5A4D) { throw 'GoW.exe is not an MZ image.' }
        $fs.Position = 0x3C
        $peOff = $br.ReadUInt32()
        $fs.Position = [int64]$peOff + 6
        $numSections = $br.ReadUInt16()
        $fs.Position = [int64]$peOff + 20
        $sizeOptional = $br.ReadUInt16()
        $optional = [int64]$peOff + 24
        $fs.Position = $optional
        if ($br.ReadUInt16() -ne 0x20B) { throw 'Expected PE32+ image.' }
        $fs.Position = $optional + 24
        $imageBase = $br.ReadUInt64()
        $sectionTable = $optional + $sizeOptional
        $sections = @()
        for ($i = 0; $i -lt $numSections; $i++) {
            $off = $sectionTable + 40 * $i
            $fs.Position = $off
            $nameBytes = $br.ReadBytes(8)
            $name = [Text.Encoding]::ASCII.GetString($nameBytes).Trim([char]0)
            $virtualSize = $br.ReadUInt32()
            $virtualAddress = $br.ReadUInt32()
            $rawSize = $br.ReadUInt32()
            $rawPtr = $br.ReadUInt32()
            $sections += [pscustomobject]@{
                Name=$name; VirtualSize=[uint64]$virtualSize; VirtualAddress=[uint64]$virtualAddress;
                RawSize=[uint64]$rawSize; RawPtr=[uint64]$rawPtr
            }
        }
        return [pscustomobject]@{ ImageBase=[uint64]$imageBase; Sections=$sections }
    }
    finally {
        if ($null -ne $br) { $br.Dispose() } else { $fs.Dispose() }
    }
}

function FileOffset-ToVa($Layout, [uint64]$FileOffset) {
    foreach ($section in $Layout.Sections) {
        if ($FileOffset -ge $section.RawPtr -and $FileOffset -lt ($section.RawPtr + $section.RawSize)) {
            $rva = $section.VirtualAddress + ($FileOffset - $section.RawPtr)
            return [pscustomobject]@{ Section=$section.Name; Rva=[uint64]$rva; Va=[uint64]($Layout.ImageBase + $rva) }
        }
    }
    throw ("File offset 0x{0:X} is not inside a PE section." -f $FileOffset)
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map native binding table xref scan ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"
    Write-Host 'Read-only GoW.exe static xref scan. Game/save/progression are not written and the game is not launched.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch. Expected '$expectedBranch', found '$branch'." }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect pre-existing staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')" }

    $exe = Join-Path ([IO.Path]::GetFullPath($GameRoot)) 'GoW.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "GoW.exe not found: $exe" }
    $before = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    $expectedHash = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
    if ($before -ne $expectedHash) { throw "Unexpected GoW.exe SHA-256. Expected $expectedHash, found $before" }

    $layout = Read-PeLayout $exe
    $targets = [ordered]@{
        table_start = [uint64]0x11C8100
        GetCounter = [uint64]0x11C8CC0
        GetRefBool = [uint64]0x11C9180
        MarkerID = [uint64]0x11C9700
        ResolveGameObject = [uint64]0x11C9B60
    }

    $mapped = @()
    $patterns = @()
    foreach ($entry in $targets.GetEnumerator()) {
        $map = FileOffset-ToVa $layout ([uint64]$entry.Value)
        $mapped += [pscustomobject]@{
            Name=[string]$entry.Key; FileOffset=('0x{0:X}' -f [uint64]$entry.Value);
            Section=$map.Section; Rva=('0x{0:X}' -f $map.Rva); Va=('0x{0:X}' -f $map.Va)
        }
        $patterns += ('0x{0:x}' -f $map.Va)
        $patterns += ('{0:x}' -f $map.Va)
    }

    $objdump = Find-Objdump
    $tempDisassembly = Join-Path $env:TEMP ("gow-text-xrefs-$stamp.txt")
    Write-Host "objdump: $objdump"
    Write-Host 'Disassembling .text once to a temporary file, then retaining only target-reference contexts.'
    & $objdump -d -M intel -j .text -- $exe 2>&1 | Set-Content -LiteralPath $tempDisassembly -Encoding ASCII
    if ($LASTEXITCODE -ne 0) { throw "objdump failed with exit code $LASTEXITCODE" }

    $out = New-Object System.Collections.Generic.List[string]
    $out.Add('Completionist Map - native binding table xref scan')
    $out.Add("exe=$exe")
    $out.Add("sha256=$before")
    $out.Add(('image_base=0x{0:X}' -f $layout.ImageBase))
    $out.Add('')
    $out.Add('Mapped descriptor targets:')
    foreach ($item in $mapped) {
        $out.Add(("{0}: file={1} section={2} rva={3} va={4}" -f $item.Name,$item.FileOffset,$item.Section,$item.Rva,$item.Va))
    }
    $out.Add('')
    $out.Add('Disassembly references:')

    $matches = @(Select-String -LiteralPath $tempDisassembly -Pattern $patterns -SimpleMatch -Context 10,18)
    if ($matches.Count -eq 0) {
        $out.Add('NO_DIRECT_OBJDUMP_TARGET_REFERENCES_FOUND')
    } else {
        foreach ($m in $matches) {
            $out.Add(('--- match line {0}: {1}' -f $m.LineNumber, $m.Line.Trim()))
            foreach ($line in $m.Context.PreContext) { $out.Add([string]$line) }
            $out.Add([string]$m.Line)
            foreach ($line in $m.Context.PostContext) { $out.Add([string]$line) }
            $out.Add('')
        }
    }
    $out.Add('')
    $out.Add("direct_match_count=$($matches.Count)")
    $out.Add('source_hashes_unchanged=true active_save_opened=false game_written=false save_or_progression_written=false game_launched=false')
    $out | Set-Content -LiteralPath $xrefPath -Encoding UTF8

    $after = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($after -ne $before) { throw 'GoW.exe hash changed during read-only scan.' }

    Write-Host "TARGET_XREF_SCAN_COMPLETED matches=$($matches.Count)"
    Write-Host "Output: $relativeLogDir"
    Publish-Scan 'SCAN_PASSED'
    Write-Host 'SCAN_PASSED_AND_PUSHED'
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Scan 'SCAN_FAILED' } catch { Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    if ($null -ne $tempDisassembly -and (Test-Path -LiteralPath $tempDisassembly)) { Remove-Item -LiteralPath $tempDisassembly -Force -ErrorAction SilentlyContinue }
    Stop-LocalTranscript
}
