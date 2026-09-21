param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [ValidateRange(10,120)][int]$StartupTimeoutSeconds = 60,
    [ValidateRange(5,60)][int]$SettleSeconds = 40
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo
if ((& git branch --show-current).Trim() -ne $ExpectedBranch) { throw "Need branch $ExpectedBranch." }
if (@(& git diff --cached --name-only).Count -gt 0) { throw 'Staged changes exist. Refuse capture.' }
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War first.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$exe = Join-Path $game 'GoW.exe'
$version = Join-Path $game 'version.dll'
$xinputLocal = Join-Path $game 'XINPUT1_4.dll'
$manifest = Join-Path $game 'mods\completionist-map\native\raven-native-bridge-manifest.json'
foreach ($p in @($exe,$version)) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Required file missing: $p" }
}
if (Test-Path -LiteralPath $xinputLocal -PathType Leaf) {
    throw "Game-root XINPUT1_4.dll exists before read-only capture; recover bridge first: $xinputLocal"
}
if (Test-Path -LiteralPath $manifest -PathType Leaf) {
    throw "Raven native bridge manifest exists before read-only capture; recover bridge first: $manifest"
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/gow-loaded-module-paths-$stamp"
$outDir = Join-Path $repo ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$report = Join-Path $outDir 'report.txt'
$json = Join-Path $outDir 'report.json'
$transcript = $false
$bootstrap = $null

if (-not ('CompletionistModuleSnapshot' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

public static class CompletionistModuleSnapshot
{
    private const uint PROCESS_VM_READ = 0x0010;
    private const uint PROCESS_QUERY_INFORMATION = 0x0400;
    private const uint LIST_MODULES_ALL = 0x03;

    [StructLayout(LayoutKind.Sequential)]
    private struct MODULEINFO
    {
        public IntPtr lpBaseOfDll;
        public uint SizeOfImage;
        public IntPtr EntryPoint;
    }

    public sealed class ModuleRow
    {
        public string Name { get; set; }
        public string Path { get; set; }
        public long BaseAddress { get; set; }
        public uint Size { get; set; }
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint dwDesiredAccess, bool bInheritHandle, uint dwProcessId);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr hObject);

    [DllImport("psapi.dll", SetLastError = true)]
    private static extern bool EnumProcessModulesEx(
        IntPtr hProcess,
        [Out] IntPtr[] lphModule,
        uint cb,
        out uint lpcbNeeded,
        uint dwFilterFlag);

    [DllImport("psapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetModuleFileNameExW(
        IntPtr hProcess,
        IntPtr hModule,
        [Out] StringBuilder lpFilename,
        uint nSize);

    [DllImport("psapi.dll", SetLastError = true)]
    private static extern bool GetModuleInformation(
        IntPtr hProcess,
        IntPtr hModule,
        out MODULEINFO lpmodinfo,
        uint cb);

    public static ModuleRow[] Enumerate(int processId)
    {
        IntPtr process = OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
            false,
            unchecked((uint)processId));

        if (process == IntPtr.Zero)
        {
            int error = Marshal.GetLastWin32Error();
            throw new Win32Exception(error, "OpenProcess failed (error " + error + ").");
        }

        try
        {
            IntPtr[] modules = new IntPtr[256];
            uint needed;

            while (true)
            {
                uint bytes = checked((uint)(modules.Length * IntPtr.Size));
                if (!EnumProcessModulesEx(process, modules, bytes, out needed, LIST_MODULES_ALL))
                {
                    int error = Marshal.GetLastWin32Error();
                    throw new Win32Exception(error, "EnumProcessModulesEx failed (error " + error + ").");
                }

                int requiredCount = checked((int)((needed + (uint)IntPtr.Size - 1) / (uint)IntPtr.Size));
                if (requiredCount <= modules.Length)
                    break;

                modules = new IntPtr[Math.Max(requiredCount, modules.Length * 2)];
            }

            int count = checked((int)(needed / (uint)IntPtr.Size));
            var rows = new List<ModuleRow>(count);

            for (int index = 0; index < count; index++)
            {
                IntPtr module = modules[index];
                if (module == IntPtr.Zero)
                    continue;

                var pathBuilder = new StringBuilder(32768);
                uint chars = GetModuleFileNameExW(process, module, pathBuilder, (uint)pathBuilder.Capacity);
                if (chars == 0)
                {
                    int error = Marshal.GetLastWin32Error();
                    throw new Win32Exception(error, "GetModuleFileNameExW failed (error " + error + ").");
                }

                MODULEINFO info;
                if (!GetModuleInformation(
                    process,
                    module,
                    out info,
                    (uint)Marshal.SizeOf(typeof(MODULEINFO))))
                {
                    int error = Marshal.GetLastWin32Error();
                    throw new Win32Exception(error, "GetModuleInformation failed (error " + error + ").");
                }

                string fullPath = pathBuilder.ToString();
                rows.Add(new ModuleRow
                {
                    Name = Path.GetFileName(fullPath) ?? string.Empty,
                    Path = fullPath,
                    BaseAddress = info.lpBaseOfDll.ToInt64(),
                    Size = info.SizeOfImage
                });
            }

            return rows.ToArray();
        }
        finally
        {
            CloseHandle(process);
        }
    }
}
'@
}

function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
}

function Get-ModuleSnapshot([System.Diagnostics.Process]$Process) {
    $rows = @()
    try {
        foreach ($module in [CompletionistModuleSnapshot]::Enumerate($Process.Id)) {
            $rows += [pscustomobject]@{
                module_name = [string]$module.Name
                file_name = [string]$module.Path
                base_address = ('0x{0:X16}' -f [int64]$module.BaseAddress)
                module_memory_size = [int64]$module.Size
            }
        }
    } catch {
        return [pscustomobject]@{ ok=$false; error=$_.Exception.Message; modules=@() }
    }
    return [pscustomobject]@{ ok=$true; error=$null; modules=@($rows) }
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true
    Write-Host 'GOW LOADED MODULE PATH CAPTURE - READ ONLY'
    Write-Host 'No native proxy is installed and no process/save/progression writes are performed.'

    $baseline = @(Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -in @('GoW','GodOfWar') } |
        Select-Object -ExpandProperty Id)

    $bootstrap = Start-Process -FilePath $exe -WorkingDirectory $game -PassThru
    $bootstrapExitCode = $null
    $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    $target = $null
    $lastModuleError = $null

    while ([DateTime]::UtcNow -lt $deadline -and $null -eq $target) {
        Start-Sleep -Milliseconds 250
        if ($null -eq $bootstrapExitCode) {
            try {
                $bootstrap.Refresh()
                if ($bootstrap.HasExited) { $bootstrapExitCode = $bootstrap.ExitCode }
            } catch {}
        }

        $candidates = @(Get-Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ProcessName -in @('GoW','GodOfWar') -and
                $baseline -notcontains $_.Id
            } |
            Sort-Object StartTime -Descending)

        foreach ($candidate in $candidates) {
            $snapshot = Get-ModuleSnapshot $candidate
            if ($snapshot.ok -and @($snapshot.modules).Count -gt 0) {
                $target = $candidate
                break
            }
            if (-not $snapshot.ok) { $lastModuleError = $snapshot.error }
        }
    }

    if ($null -eq $target) {
        $exitText = if ($null -eq $bootstrapExitCode) { 'unknown_or_running' } else { [string]$bootstrapExitCode }
        throw "No readable long-lived GoW process appeared within $StartupTimeoutSeconds seconds. bootstrap_exit_code=$exitText last_module_error=$lastModuleError"
    }

    Write-Host "Live GoW process found: PID=$($target.Id). Waiting $SettleSeconds seconds for modules to settle..."
    Start-Sleep -Seconds $SettleSeconds

    $snapshot = Get-ModuleSnapshot $target
    if (-not $snapshot.ok) { throw "Module enumeration failed for PID $($target.Id): $($snapshot.error)" }

    $modules = @($snapshot.modules | Sort-Object module_name, file_name)
    $xinput = @($modules | Where-Object { $_.module_name -ieq 'XINPUT1_4.dll' })
    $versionModules = @($modules | Where-Object { $_.module_name -ieq 'version.dll' })
    $dxgi = @($modules | Where-Object { $_.module_name -ieq 'dxgi.dll' })

    $result = [ordered]@{
        schema = 1
        captured_utc = (Get-Date).ToUniversalTime().ToString('o')
        branch = $ExpectedBranch
        game_root = $game
        bootstrap_pid = $bootstrap.Id
        bootstrap_exit_code = if ($null -eq $bootstrapExitCode) { $null } else { [int]$bootstrapExitCode }
        game_pid = $target.Id
        module_count = @($modules).Count
        xinput1_4_count = @($xinput).Count
        xinput1_4 = @($xinput)
        version_count = @($versionModules).Count
        version = @($versionModules)
        dxgi_count = @($dxgi).Count
        dxgi = @($dxgi)
        modules = @($modules)
        safety = [ordered]@{
            read_only = $true
            process_writes = $false
            save_writes = $false
            progression_writes = $false
            game_files_written = $false
            proxy_installed = $false
        }
    }
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $json -Encoding UTF8

    $lines = @(
        'Completionist Map - GoW loaded module path capture'
        "captured_utc=$($result.captured_utc)"
        "bootstrap_pid=$($result.bootstrap_pid)"
        "bootstrap_exit_code=$(if ($null -eq $result.bootstrap_exit_code) { 'n/a' } else { $result.bootstrap_exit_code })"
        "game_pid=$($result.game_pid)"
        "module_count=$($result.module_count)"
        "xinput1_4_count=$($result.xinput1_4_count)"
    )
    if (@($xinput).Count -eq 0) {
        $lines += 'XINPUT1_4 NONE'
    } else {
        foreach ($m in $xinput) { $lines += "XINPUT1_4 $($m.file_name)" }
    }
    $lines += "version_count=$($result.version_count)"
    foreach ($m in $versionModules) { $lines += "VERSION $($m.file_name)" }
    $lines += "dxgi_count=$($result.dxgi_count)"
    foreach ($m in $dxgi) { $lines += "DXGI $($m.file_name)" }
    $lines += ''
    $lines += 'ALL_MODULES'
    foreach ($m in $modules) { $lines += ($m.module_name + [char]9 + $m.file_name) }
    $lines += ''
    $lines += 'SAFETY read_only=true process_writes=false save_writes=false progression_writes=false game_files_written=false proxy_installed=false'
    $lines | Set-Content -LiteralPath $report -Encoding UTF8

    Write-Host "GOW_MODULE_PATH_CAPTURE_COMPLETE pid=$($target.Id) modules=$(@($modules).Count) xinput1_4=$(@($xinput).Count)"
    foreach ($m in $xinput) { Write-Host "XINPUT1_4 $($m.file_name)" }
    foreach ($m in $versionModules) { Write-Host "VERSION $($m.file_name)" }
    foreach ($m in $dxgi) { Write-Host "DXGI $($m.file_name)" }

    Read-Host 'Capture complete. Quit GoW fully, then press Enter' | Out-Null
    if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
        throw 'GoW is still running. Quit it fully before evidence push.'
    }

    Stop-LocalTranscript
    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add capture failed.' }
    & git commit -m "research(v0.10.5): capture live GoW loaded module paths $stamp" -- $relativeDir | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git commit capture failed.' }
    & git push origin $ExpectedBranch | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git push capture failed.' }

    Write-Host "GOW_MODULE_PATH_CAPTURE_PUSHED $((& git rev-parse HEAD).Trim())"
    Write-Host "Evidence: $relativeDir"
}
catch {
    $outer = $_
    try { $outer.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Stop-LocalTranscript
    try {
        & git add -f -- $relativeDir
        if ($LASTEXITCODE -eq 0) {
            & git commit -m "research(v0.10.5): archive failed live module-path capture $stamp" -- $relativeDir | Out-Host
            if ($LASTEXITCODE -eq 0) { & git push origin $ExpectedBranch | Out-Host }
        }
    } catch {}
    throw
}
finally {
    Stop-LocalTranscript
}
