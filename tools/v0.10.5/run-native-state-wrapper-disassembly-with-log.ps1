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
$relativeLogDir = "archive/field-logs/source-scans/native-state-wrapper-disassembly-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$disassemblyPath = Join-Path $logDir 'wrappers-disassembly.txt'
$summaryPath = Join-Path $logDir 'summary.json'
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

    & git commit -m "Archive native state wrapper disassembly $stamp" -- $relativeLogDir
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
    throw 'GNU objdump.exe not found. Git for Windows normally ships it under Program Files\Git\usr\bin or mingw64\bin.'
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map targeted native state-wrapper disassembly ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"
    Write-Host 'Read-only GoW.exe disassembly. Game/save/progression are not written and the game is not launched.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) {
        throw "Wrong branch. Expected '$expectedBranch', found '$branch'."
    }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect pre-existing staged changes.' }
    if ($staged.Count -gt 0) {
        throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')"
    }

    $game = [IO.Path]::GetFullPath($GameRoot)
    $exe = Join-Path $game 'GoW.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "GoW.exe not found: $exe" }

    $before = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    $expectedHash = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
    if ($before -ne $expectedHash) {
        throw "Unexpected GoW.exe SHA-256. Expected $expectedHash, found $before"
    }

    $fs = [IO.File]::Open($exe, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $br = New-Object IO.BinaryReader($fs)
        if ($br.ReadUInt16() -ne 0x5A4D) { throw 'GoW.exe is not an MZ image.' }
        $fs.Position = 0x3C
        $peOff = $br.ReadUInt32()
        $fs.Position = [int64]$peOff + 24 + 24
        $imageBase = $br.ReadUInt64()
    }
    finally {
        if ($null -ne $br) { $br.Dispose() } else { $fs.Dispose() }
    }

    $objdump = Find-Objdump
    Write-Host "objdump: $objdump"
    Write-Host ("imageBase=0x{0:X}" -f $imageBase)

    $targets = [ordered]@{
        GetVariable = 0x787C60
        GetCounterName = 0x841A80
        GetCounterChild = 0x841CE0
        GetCounterChildrenCount = 0x841D50
        GetCounter = 0x841E50
        GetRefString = 0x8456A0
        GetRefInt = 0x8456C0
        GetRefFloat = 0x8456E0
        GetRefBool = 0x845700
        GetRegionHash = 0x847170
        EntityBool = 0x84B3B0
        MarkerID = 0x84F6F0
        ResolveGameObject = 0x84F750
    }

    $lines = New-Object System.Collections.Generic.List[string]
    $records = New-Object System.Collections.Generic.List[object]
    foreach ($entry in $targets.GetEnumerator()) {
        $name = [string]$entry.Key
        $rva = [uint64]$entry.Value
        $start = [uint64]($imageBase + $rva)
        $stop = [uint64]($start + 0x100)
        $startArg = '--start-address=0x' + $start.ToString('X')
        $stopArg = '--stop-address=0x' + $stop.ToString('X')

        $lines.Add(('===== {0} RVA=0x{1:X} VA=0x{2:X} =====' -f $name, $rva, $start))
        $out = @(& $objdump -d -M intel $startArg $stopArg -- $exe 2>&1)
        $code = $LASTEXITCODE
        if ($code -ne 0) {
            throw "objdump failed for $name with exit code $code"
        }
        foreach ($line in $out) { $lines.Add([string]$line) }
        $lines.Add('')
        $records.Add([pscustomobject]@{
            name = $name
            rva = ('0x{0:X}' -f $rva)
            va = ('0x{0:X}' -f $start)
            bytes_requested = 256
        })
    }

    $lines | Set-Content -LiteralPath $disassemblyPath -Encoding UTF8

    $after = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($after -ne $before) { throw 'GoW.exe hash changed during read-only disassembly.' }

    $summary = [ordered]@{
        schema = 1
        generated_at = (Get-Date -Format o)
        branch = $branch
        exe = $exe
        exe_sha256 = $before
        image_base = ('0x{0:X}' -f $imageBase)
        disassembler = $objdump
        known_baseline = 'GetVariable is proven by shipped Lua usage as a one-string getter: game.Level.GetVariable("name")'
        targets = @($records)
        safety = [ordered]@{
            scan_only = $true
            active_save_opened = $false
            game_written = $false
            save_or_progression_written = $false
            game_launched = $false
            source_hash_unchanged = $true
        }
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding UTF8

    Write-Host "Disassembled $($records.Count) targeted wrappers."
    Write-Host "Output: $relativeLogDir"
    Write-Host 'NATIVE_STATE_WRAPPER_DISASSEMBLY_COMPLETED'
    Publish-Scan 'SCAN_PASSED'
    Write-Host 'SCAN_PASSED_AND_PUSHED'
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Scan 'SCAN_FAILED' } catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 1
}
finally {
    Stop-LocalTranscript
}
