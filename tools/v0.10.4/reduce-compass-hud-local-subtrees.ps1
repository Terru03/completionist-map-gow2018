param(
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
$script = Join-Path $PSScriptRoot 'reduce-compass-hud-local-subtrees.py'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Missing reducer: $script" }

$sourceRel = 'archive/field-logs/completionist-v104-compass-hud-gameobject-chain.json'
$source = Join-Path $repo ($sourceRel -replace '/', '\')
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Missing archived compass HUD chain report: $source"
}

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v104-compass-hud-local-subtrees.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

Write-Host 'Syntax-checking compass HUD local-subtree reducer...'
$sourceCode = [IO.File]::ReadAllText($script)
$sourceCode | & $python.Source -c 'import ast,sys; ast.parse(sys.stdin.read())'
if ($LASTEXITCODE -ne 0) { throw 'Compass HUD local-subtree reducer syntax check failed.' }

Write-Host 'Reducing archived compass HUD trace to class-local subtrees...'
& $python.Source $script --input $source --output $out
if ($LASTEXITCODE -ne 0) { throw 'Compass HUD local-subtree reduction failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw 'Compass HUD local-subtree report was not created.' }

$report = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ([string]$report.result -ne 'REPORT_ONLY_COMPASS_HUD_LOCAL_SUBTREES' -or
    $report.game_files_read -ne $false -or
    $report.game_files_written -ne $false -or
    $report.save_state_written -ne $false -or
    $report.progression_state_written -ne $false -or
    $report.marker_state_written -ne $false -or
    $report.stock_root_contract_shared -ne $true -or
    [string]$report.conclusion -ne 'DOCK_LOCAL_HUD_SUBTREE_ISOLATED') {
    throw 'Compass HUD local-subtree report failed safety/result validation.'
}

$dock = $report.dock_local_contract
Write-Host ''
Write-Host 'Compass HUD local-subtree reduction complete.'
Write-Host ("- Dock root: {0}" -f [string]$dock.root)
Write-Host ("- Dock prototype: {0}" -f [string]$dock.prototype)
Write-Host ("- Dock models: {0}" -f (@($dock.models) -join ', '))
Write-Host ("- Dock materials: {0}" -f (@($dock.materials) -join ', '))
Write-Host ("- Dock meshes: {0}" -f (@($dock.meshes) -join ', '))
Write-Host ("- Dock artwork textures: {0}" -f (@($dock.artwork_textures) -join ', '))
Write-Host ("- shared compass: {0}" -f [string]$dock.shared_compass)
Write-Host ("- conclusion: {0}" -f [string]$report.conclusion)
Write-Host ("- report: {0}" -f $out)
Write-Host '- game files read: false'
Write-Host '- game files written: false'

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Compass HUD local-subtree report unchanged; nothing new to commit.'
    } else {
        git commit -m 'Archive compass HUD local subtrees' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Report committed and pushed to $Remote/$branch."
    }
} finally {
    Pop-Location
}
