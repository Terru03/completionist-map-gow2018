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
$relativeLogDir = "archive/field-logs/source-scans/native-binding-registration-context-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$reportPath = Join-Path $logDir 'registration-context.txt'
$published = $false
$transcriptStarted = $false

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
    & git commit -m "Archive native binding registration context $stamp" -- $relativeLogDir
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

function Va-ToFileOffset($Layout, [uint64]$Va) {
    if ($Va -lt $Layout.ImageBase) { return $null }
    $rva = $Va - $Layout.ImageBase
    foreach ($section in $Layout.Sections) {
        $span = [Math]::Max([double]$section.VirtualSize, [double]$section.RawSize)
        if ($rva -ge $section.VirtualAddress -and $rva -lt ($section.VirtualAddress + [uint64]$span)) {
            $delta = $rva - $section.VirtualAddress
            if ($delta -ge $section.RawSize) { return $null }
            return [pscustomobject]@{ Offset=[uint64]($section.RawPtr + $delta); Section=$section.Name; Rva=[uint64]$rva }
        }
    }
    return $null
}

function Read-AsciiAtVa([string]$ExePath, $Layout, [uint64]$Va) {
    $mapped = Va-ToFileOffset $Layout $Va
    if ($null -eq $mapped) { return $null }
    $fs = [IO.File]::Open($ExePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $fs.Position = [int64]$mapped.Offset
        $bytes = New-Object System.Collections.Generic.List[byte]
        for ($i = 0; $i -lt 192; $i++) {
            $b = $fs.ReadByte()
            if ($b -lt 0) { return $null }
            if ($b -eq 0) { break }
            if ($b -lt 0x20 -or $b -gt 0x7E) { return $null }
            $bytes.Add([byte]$b)
        }
        if ($bytes.Count -lt 2) { return $null }
        return [Text.Encoding]::ASCII.GetString($bytes.ToArray())
    }
    finally { $fs.Dispose() }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map native binding registration-context scan ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"
    Write-Host 'Read-only static probe. Game/save/progression are not written and the game is not launched.'

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

    $objdump = Find-Objdump
    $layout = Read-PeLayout $exe
    $out = New-Object System.Collections.Generic.List[string]
    $out.Add('Completionist Map - native binding registration-context scan')
    $out.Add("exe=$exe")
    $out.Add("sha256=$before")
    $out.Add('known_function_descriptor_count=309')
    $out.Add('known_property_descriptor_count=86')
    $out.Add('descriptor_stride=32')
    $out.Add('function_table_va=0x1411CA300')
    $out.Add('function_registration_callback_va=0x1407BA4D0')
    $out.Add('property_registration_callback_va=0x1407BA4A0')
    $out.Add('')

    $ranges = @(
        [pscustomobject]@{Name='registration_thunk_and_callbacks'; Start='0x1407BA420'; Stop='0x1407BA560'},
        [pscustomobject]@{Name='first_registration_caller'; Start='0x1407B98D0'; Stop='0x1407B9A30'},
        [pscustomobject]@{Name='startup_registration_caller'; Start='0x1407BE560'; Stop='0x1407BE730'}
    )

    $allDisasm = New-Object System.Collections.Generic.List[string]
    foreach ($range in $ranges) {
        $out.Add("=== $($range.Name) $($range.Start)-$($range.Stop) ===")
        $lines = @(& $objdump -d -M intel -j .text --start-address=$($range.Start) --stop-address=$($range.Stop) -- $exe 2>&1)
        if ($LASTEXITCODE -ne 0) { throw "objdump failed for $($range.Name) with exit code $LASTEXITCODE" }
        foreach ($line in $lines) {
            $text = [string]$line
            $out.Add($text)
            $allDisasm.Add($text)
        }
        $out.Add('')
    }

    $targets = New-Object 'System.Collections.Generic.HashSet[UInt64]'
    foreach ($line in $allDisasm) {
        foreach ($m in [regex]::Matches($line, '#\s+0x(?<hex>14[0-9a-fA-F]+)')) {
            [uint64]$value = [Convert]::ToUInt64($m.Groups['hex'].Value, 16)
            [void]$targets.Add($value)
        }
    }
    $out.Add('=== referenced printable strings ===')
    $stringCount = 0
    foreach ($va in ($targets | Sort-Object)) {
        $s = Read-AsciiAtVa $exe $layout $va
        if ($null -ne $s) {
            $mapped = Va-ToFileOffset $layout $va
            $out.Add(('va=0x{0:X} section={1} file=0x{2:X} string={3}' -f $va,$mapped.Section,$mapped.Offset,$s))
            $stringCount++
        }
    }
    if ($stringCount -eq 0) { $out.Add('NO_PRINTABLE_STRING_TARGETS_IN_SELECTED_RANGES') }
    $out.Add('')

    $out.Add('=== import/IAT context ===')
    $imports = @(& $objdump -p -- $exe 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "objdump -p failed with exit code $LASTEXITCODE" }
    $importMatches = @($imports | Select-String -Pattern 'd49058|d49060|lua|script' -CaseSensitive:$false -Context 2,2)
    if ($importMatches.Count -eq 0) {
        $out.Add('NO_IMPORT_METADATA_MATCH_FOR_D49058_D49060_OR_LUA_SCRIPT')
    } else {
        foreach ($m in $importMatches) {
            foreach ($line in $m.Context.PreContext) { $out.Add([string]$line) }
            $out.Add([string]$m.Line)
            foreach ($line in $m.Context.PostContext) { $out.Add([string]$line) }
            $out.Add('')
        }
    }

    $out.Add('=== shipped Lua representative call forms ===')
    $names = @('GetCounter','GetCounterChild','GetCounterChildrenCount','GetCounterName','GetRefBool','ResolveGameObject','MarkerID','GetRegionHash','EntityBool','EventID','Hash','Random','Sqrt','Min','Max','QueryTimer','StartTimer','SaveGame','CheckPoint')
    $luaFiles = @(Get-ChildItem -LiteralPath $GameRoot -Recurse -File -Filter '*.lua' -ErrorAction SilentlyContinue)
    $out.Add("lua_files_scanned=$($luaFiles.Count)")
    $callHits = 0
    foreach ($file in $luaFiles) {
        $lineNo = 0
        foreach ($line in [IO.File]::ReadLines($file.FullName)) {
            $lineNo++
            foreach ($name in $names) {
                $pattern = '(?<![A-Za-z0-9_])(?<expr>(?:[A-Za-z_][A-Za-z0-9_]*\.)*' + [regex]::Escape($name) + ')\s*\('
                foreach ($m in [regex]::Matches($line, $pattern)) {
                    $relative = $file.FullName.Substring(([IO.Path]::GetFullPath($GameRoot)).TrimEnd('\').Length).TrimStart('\')
                    $out.Add("$relative`:$lineNo expr=$($m.Groups['expr'].Value) text=$($line.Trim())")
                    $callHits++
                }
            }
        }
    }
    if ($callHits -eq 0) { $out.Add('NO_REPRESENTATIVE_CALL_FORMS_FOUND') }
    $out.Add("representative_call_hits=$callHits")
    $out.Add('')
    $out.Add('source_hashes_unchanged=true active_save_opened=false game_written=false save_or_progression_written=false game_launched=false')

    $out | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $after = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($after -ne $before) { throw 'GoW.exe hash changed during read-only scan.' }

    Write-Host "REGISTRATION_CONTEXT_SCAN_COMPLETED strings=$stringCount callHits=$callHits"
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
    Stop-LocalTranscript
}
