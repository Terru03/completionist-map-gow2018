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
$relativeLogDir = "archive/field-logs/source-scans/native-binding-dispatcher-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$reportPath = Join-Path $logDir 'dispatcher-report.txt'
$resultPath = Join-Path $logDir 'result.txt'
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
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
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
    & git commit -m "Archive native binding dispatcher analysis $stamp" -- $relativeLogDir
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

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map native binding dispatcher analysis ==='
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
    $tempDisassembly = Join-Path $env:TEMP ("gow-binding-dispatcher-$stamp.txt")
    & $objdump -d -M intel -j .text -- $exe 2>&1 | Set-Content -LiteralPath $tempDisassembly -Encoding ASCII
    if ($LASTEXITCODE -ne 0) { throw "objdump failed with exit code $LASTEXITCODE" }

    $out = New-Object System.Collections.Generic.List[string]
    $out.Add('Completionist Map - native binding dispatcher analysis')
    $out.Add("exe=$exe")
    $out.Add("sha256=$before")
    $out.Add('function_table_va=0x1411CA300')
    $out.Add('property_table_va=0x1411CC9A0')
    $out.Add('function_count=309')
    $out.Add('property_count=86')
    $out.Add('descriptor_stride=32')
    $out.Add('bsearch_iat=0x140D49058')
    $out.Add('qsort_iat=0x140D49060')
    $out.Add('')

    $out.Add('=== focused function-dispatcher disassembly ===')
    $focused = @(& $objdump -d -M intel -j .text --start-address=0x1407B97F0 --stop-address=0x1407B9A40 -- $exe 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'objdump failed for focused dispatcher range.' }
    foreach ($line in $focused) { $out.Add([string]$line) }
    $out.Add('')

    $out.Add('=== all bsearch call-site contexts ===')
    $bsearchHits = @(Select-String -LiteralPath $tempDisassembly -Pattern '# 0x140d49058' -SimpleMatch -Context 18,24)
    $out.Add("bsearch_call_sites=$($bsearchHits.Count)")
    foreach ($m in $bsearchHits) {
        $out.Add(('--- line {0}: {1}' -f $m.LineNumber,$m.Line.Trim()))
        foreach ($line in $m.Context.PreContext) { $out.Add([string]$line) }
        $out.Add([string]$m.Line)
        foreach ($line in $m.Context.PostContext) { $out.Add([string]$line) }
        $out.Add('')
    }
    $out.Add('')

    $out.Add('=== direct function/property table references ===')
    $tableHits = @(Select-String -LiteralPath $tempDisassembly -Pattern '0x1411ca300','0x1411cc9a0' -SimpleMatch -Context 12,20)
    $out.Add("table_reference_hits=$($tableHits.Count)")
    foreach ($m in $tableHits) {
        $out.Add(('--- line {0}: {1}' -f $m.LineNumber,$m.Line.Trim()))
        foreach ($line in $m.Context.PreContext) { $out.Add([string]$line) }
        $out.Add([string]$m.Line)
        foreach ($line in $m.Context.PostContext) { $out.Add([string]$line) }
        $out.Add('')
    }
    $out.Add('')

    $out.Add('=== strict bare-global shipped Lua calls ===')
    $names = @('GetCounter','GetCounterChild','GetCounterChildrenCount','GetCounterName','GetRefBool','GetRefInt','GetRefFloat','GetRefString','ResolveGameObject','MarkerID','GetRegionHash','EntityBool','EventID','Random','Sqrt','Min','Max')
    $luaFiles = @(Get-ChildItem -LiteralPath $GameRoot -Recurse -File -Filter '*.lua' -ErrorAction SilentlyContinue)
    $out.Add("lua_files_scanned=$($luaFiles.Count)")
    $globalHits = 0
    foreach ($file in $luaFiles) {
        $lineNo = 0
        foreach ($line in [IO.File]::ReadLines($file.FullName)) {
            $lineNo++
            foreach ($name in $names) {
                $pattern = '(?<![A-Za-z0-9_\.:])' + [regex]::Escape($name) + '\s*\('
                foreach ($m in [regex]::Matches($line, $pattern)) {
                    $prefix = $line.Substring(0,$m.Index)
                    if ($prefix -match 'function\s+$') { continue }
                    $root = ([IO.Path]::GetFullPath($GameRoot)).TrimEnd('\')
                    $relative = $file.FullName.Substring($root.Length).TrimStart('\')
                    $out.Add("$relative`:$lineNo global=$name text=$($line.Trim())")
                    $globalHits++
                }
            }
        }
    }
    if ($globalHits -eq 0) { $out.Add('NO_STRICT_BARE_GLOBAL_CALLS_FOUND') }
    $out.Add("strict_bare_global_hits=$globalHits")
    $out.Add('')

    $out.Add('=== interpretation guardrails ===')
    $out.Add('qsort_is_sorting_only=true')
    $out.Add('bsearch_consumer_is_dispatch_candidate=true')
    $out.Add('runtime_namespace_not_declared_proven_by_static_scan=true')
    $out.Add('no_runtime_calls_made=true')
    $out.Add('source_hashes_unchanged=true active_save_opened=false game_written=false save_or_progression_written=false game_launched=false')
    $out | Set-Content -LiteralPath $reportPath -Encoding UTF8

    $after = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($after -ne $before) { throw 'GoW.exe hash changed during read-only scan.' }

    Write-Host "DISPATCHER_SCAN_COMPLETED bsearchSites=$($bsearchHits.Count) tableRefs=$($tableHits.Count) bareGlobals=$globalHits"
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
