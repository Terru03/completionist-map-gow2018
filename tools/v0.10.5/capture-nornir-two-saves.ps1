[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$SaveRoot = (Join-Path $env:USERPROFILE 'Saved Games\God of War'),
    [string]$OutRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not [Environment]::Is64BitProcess) {
    throw 'Run this capture from 64-bit Windows PowerShell.'
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$workspaceRoot = Split-Path -Parent $repoRoot
if ([string]::IsNullOrWhiteSpace($OutRoot)) {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
    $OutRoot = Join-Path $workspaceRoot "nornir-captures\$stamp"
}
$OutRoot = [IO.Path]::GetFullPath($OutRoot)
$gameFull = [IO.Path]::GetFullPath($GameRoot)
$saveFull = [IO.Path]::GetFullPath($SaveRoot)
if ($OutRoot.StartsWith($gameFull + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase) -or
    $OutRoot.StartsWith($saveFull + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Capture output must be outside the game and active save directories.'
}
if (-not (Test-Path -LiteralPath (Join-Path $GameRoot 'GoW.exe') -PathType Leaf)) {
    throw "God of War executable is missing from $GameRoot"
}
if (-not (Test-Path -LiteralPath $SaveRoot -PathType Container)) {
    throw "God of War save directory is missing: $SaveRoot"
}
$script:exeSha256 = (Get-FileHash -LiteralPath (Join-Path $GameRoot 'GoW.exe') -Algorithm SHA256).Hash.ToLowerInvariant()

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
namespace NornirCapture {
    public static class Native {
        [DllImport("Dbghelp.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool MiniDumpWriteDump(
            IntPtr processHandle, UInt32 processId, SafeFileHandle outputHandle,
            UInt32 dumpType, IntPtr exceptionParam, IntPtr userStreamParam,
            IntPtr callbackParam);
    }
}
'@

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null
$script:saveAProcessId = $null
$script:saveAStartUtc = $null
$script:saveBProcessId = $null
$script:saveBStartUtc = $null

function Get-OneGameProcess {
    $matches = @(Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') })
    if ($matches.Count -ne 1) {
        throw "Expected exactly one running God of War process; found $($matches.Count)."
    }
    return $matches[0]
}

function Copy-ActiveSave([string]$destination) {
    $saves = @(Get-ChildItem -LiteralPath $SaveRoot -Filter 'game.sav' -File -Recurse)
    if ($saves.Count -ne 1) {
        throw "Expected exactly one active game.sav; found $($saves.Count)."
    }
    $sourcePath = $saves[0].FullName
    $stable = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $before = Get-Item -LiteralPath $sourcePath
        $reader = [IO.FileStream]::new(
            $sourcePath, [IO.FileMode]::Open, [IO.FileAccess]::Read,
            ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
        try {
            $writer = [IO.FileStream]::new(
                $destination, [IO.FileMode]::Create, [IO.FileAccess]::Write,
                [IO.FileShare]::None)
            try { $reader.CopyTo($writer) } finally { $writer.Dispose() }
        } finally { $reader.Dispose() }
        $after = Get-Item -LiteralPath $sourcePath
        $stable = ($before.Length -eq $after.Length -and
                   $before.LastWriteTimeUtc -eq $after.LastWriteTimeUtc)
        if ($stable) { break }
    }
    return [ordered]@{
        source = $sourcePath
        bytes = (Get-Item -LiteralPath $destination).Length
        sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        source_stable_during_copy = $stable
    }
}

function Invoke-Capture([string]$stage, [string]$saveLabel, [string]$note) {
    $gameProcess = Get-OneGameProcess
    $startedUtc = $gameProcess.StartTime.ToUniversalTime()
    if ($saveLabel -eq 'A') {
        if ($null -eq $script:saveAProcessId) {
            $script:saveAProcessId = $gameProcess.Id
            $script:saveAStartUtc = $startedUtc
        } elseif ($script:saveAProcessId -ne $gameProcess.Id -or
                  $script:saveAStartUtc -ne $startedUtc) {
            throw 'Save A process changed between capture stages.'
        }
    } else {
        if ($null -eq $script:saveBProcessId) {
            if ($startedUtc -le $script:saveAStartUtc) {
                throw 'Save B must be loaded after restarting God of War.'
            }
            $script:saveBProcessId = $gameProcess.Id
            $script:saveBStartUtc = $startedUtc
        } elseif ($script:saveBProcessId -ne $gameProcess.Id -or
                  $script:saveBStartUtc -ne $startedUtc) {
            throw 'Save B process changed between capture stages.'
        }
    }

    $dumpPath = Join-Path $OutRoot "$stage.dmp"
    $savePath = Join-Path $OutRoot "$stage.game.sav"
    $metadataPath = Join-Path $OutRoot "$stage.json"
    if (Test-Path -LiteralPath $dumpPath) { throw "Capture already exists: $dumpPath" }
    $capturedUtc = (Get-Date).ToUniversalTime().ToString('o')
    Write-Host "Capturing $stage from process $($gameProcess.Id). The game may pause while memory is copied..." -ForegroundColor Cyan
    $output = [IO.FileStream]::new(
        $dumpPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write,
        [IO.FileShare]::None)
    try {
        # Full readable memory plus memory-map metadata; inaccessible pages are skipped.
        $dumpType = [uint32]0x00020802
        $ok = [NornirCapture.Native]::MiniDumpWriteDump(
            $gameProcess.Handle, [uint32]$gameProcess.Id, $output.SafeFileHandle,
            $dumpType, [IntPtr]::Zero, [IntPtr]::Zero, [IntPtr]::Zero)
        if (-not $ok) {
            $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            throw "MiniDumpWriteDump failed for $stage with Win32 error $code."
        }
    } finally { $output.Dispose() }

    try {
        $saveCopy = Copy-ActiveSave $savePath
    } catch {
        $saveCopy = [ordered]@{
            source = $SaveRoot
            copied = $false
            error = $_.Exception.Message
        }
    }
    $loaderLog = Join-Path $GameRoot 'mods\loader_log.txt'
    $loaderLogCopy = 'absent'
    if (Test-Path -LiteralPath $loaderLog -PathType Leaf) {
        try {
            Copy-Item -LiteralPath $loaderLog -Destination (Join-Path $OutRoot "$stage.loader_log.txt")
            $loaderLogCopy = 'copied'
        } catch {
            $loaderLogCopy = "copy_failed: $($_.Exception.Message)"
        }
    }
    $saveFileName = $null
    if (Test-Path -LiteralPath $savePath -PathType Leaf) {
        $saveFileName = [IO.Path]::GetFileName($savePath)
    }
    $moduleBase = $null
    try { $moduleBase = ('0x{0:X}' -f $gameProcess.MainModule.BaseAddress.ToInt64()) } catch {}
    $metadata = [ordered]@{
        schema = 1
        stage = $stage
        save_label = $saveLabel
        note = $note
        captured_utc = $capturedUtc
        process_id = $gameProcess.Id
        process_start_utc = $startedUtc.ToString('o')
        executable_path = $gameProcess.Path
        executable_sha256 = $script:exeSha256
        module_base = $moduleBase
        dump_type = 'MiniDumpWithFullMemory|MiniDumpWithFullMemoryInfo|MiniDumpIgnoreInaccessibleMemory'
        dump_file = [IO.Path]::GetFileName($dumpPath)
        dump_bytes = (Get-Item -LiteralPath $dumpPath).Length
        save_file = $saveFileName
        save = $saveCopy
        loader_log_copy = $loaderLogCopy
        game_process_written_by_capture = $false
        game_save_written_by_capture = $false
    }
    $metadata | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath $metadataPath -Encoding UTF8
    Write-Host "Captured ${stage}: $([math]::Round($metadata.dump_bytes / 1GB, 2)) GiB -> $OutRoot" -ForegroundColor Green
}

try {
    Write-Host "Output: $OutRoot" -ForegroundColor Cyan
    Write-Host 'Leave this PowerShell window open. Pause the game at each stage, Alt-Tab here, then press Enter.'
    $saveANote = Read-Host 'Short location/name for Save A chest (optional)'
    Read-Host 'Load Save A with the chest locked, before breaking either of the two runes; press Enter' | Out-Null
    Invoke-Capture 'A0_before_runes' 'A' $saveANote
    Read-Host 'Break the first rune, pause, then press Enter' | Out-Null
    Invoke-Capture 'A1_after_first_rune' 'A' $saveANote
    Read-Host 'Break the second rune, pause, then press Enter' | Out-Null
    Invoke-Capture 'A2_after_second_rune' 'A' $saveANote
    Read-Host 'Open the Nornir chest, wait for saving to finish, pause, then press Enter' | Out-Null
    Invoke-Capture 'A3_after_chest_open' 'A' $saveANote

    while ($true) {
        Read-Host 'Quit God of War completely before Save B, then press Enter' | Out-Null
        $running = @(Get-Process -ErrorAction SilentlyContinue |
            Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') })
        if ($running.Count -eq 0) { break }
        Write-Host 'God of War is still running.' -ForegroundColor Yellow
    }
    $saveBNote = Read-Host 'Short location/name for Save B chest (optional)'
    Read-Host 'Restart God of War, load Save B with its chest ready to open, then press Enter' | Out-Null
    Invoke-Capture 'B0_before_chest_open' 'B' $saveBNote
    Read-Host 'Open the Save B chest, wait for saving to finish, pause, then press Enter' | Out-Null
    Invoke-Capture 'B1_after_chest_open' 'B' $saveBNote

    [ordered]@{
        result = 'NORNIR_TWO_SAVE_CAPTURE_COMPLETE'
        output = $OutRoot
        stages = @('A0_before_runes', 'A1_after_first_rune',
                   'A2_after_second_rune', 'A3_after_chest_open',
                   'B0_before_chest_open', 'B1_after_chest_open')
        game_files_written_by_capture = $false
        save_files_written_by_capture = $false
    } | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath (Join-Path $OutRoot 'session.json') -Encoding UTF8
    Write-Host "NORNIR_TWO_SAVE_CAPTURE_COMPLETE $OutRoot" -ForegroundColor Green
} catch {
    $errorText = $_.Exception.ToString()
    $errorText | Set-Content -LiteralPath (Join-Path $OutRoot 'capture-error.txt') -Encoding UTF8
    Write-Host "NORNIR_CAPTURE_STOPPED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Completed stages remain in $OutRoot" -ForegroundColor Yellow
    throw
}
