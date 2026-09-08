param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin',
    [switch]$NoPublish
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before the tweak-registry initialization trace.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$scanner = Join-Path $PSScriptRoot 'inspect-tweak-registry-slot-initialization.py'
$outRel = 'archive/field-logs/completionist-v104-tweak-registry-slot-initialization.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) { throw "Missing scanner: $scanner" }
if (-not (Test-Path -LiteralPath $game -PathType Container)) { throw "Missing game root: $game" }
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$preStaged = @(& git -C $repo diff --cached --name-only)
if ($preStaged.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace(($preStaged -join ''))) {
    throw "Git index already has staged changes. Commit/unstage them before running this archive helper.`n$($preStaged -join "`n")"
}

Write-Host 'Syntax-checking tweak-registry initialization tracer...'
& $python.Source -m py_compile $scanner
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed.' }

Write-Host 'Tracing registry slot 0x22C6948 initialization/ownership read-only...'
& $python.Source $scanner --game-root $game --output $out
if ($LASTEXITCODE -ne 0) { throw 'Tweak-registry initialization trace failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw "Report was not produced: $out" }

$r = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ([string]$r.result -ne 'READ_ONLY_TWEAK_REGISTRY_SLOT_INITIALIZATION_TRACE') {
    throw "Unexpected trace result: $($r.result)"
}
if ($r.game_files_written -ne $false -or $r.save_progression_marker_state_written -ne $false) {
    throw 'Read-only safety flags failed.'
}

Write-Host ''
Write-Host 'Tweak-registry initialization trace complete.'
Write-Host ("- registry slot: {0}" -f [string]$r.registry_slot.rva)
Write-Host ("- exact accesses: {0}; reads={1}; writes={2}; address-takes={3}" -f [int]$r.registry_slot.exact_access_count, [int]$r.registry_slot.reads, [int]$r.registry_slot.writes, [int]$r.registry_slot.address_takes)
Write-Host ("- direct owner functions: {0}" -f @($r.direct_initializer_or_address_owner_functions).Count)
Write-Host ("- nearby owner functions: {0}" -f @($r.nearby_write_or_address_owner_functions).Count)
Write-Host ("- conclusion: {0}" -f [string]$r.conclusion)
Write-Host ("- report: {0}" -f $out)
Write-Host '- game files written: false'

if ($NoPublish) {
    Write-Host 'Report publishing skipped (-NoPublish).'
    return
}

& git -C $repo add -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
& git -C $repo diff --cached --check -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
& git -C $repo diff --cached --quiet -- $outRel
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Report unchanged; nothing new to commit.'
    return
}

& git -C $repo commit -m 'Archive tweak registry initialization trace' -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
& git -C $repo push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
Write-Host "Report committed and pushed to $Remote/$branch."
