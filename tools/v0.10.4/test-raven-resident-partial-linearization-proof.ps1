param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$testRoot = Join-Path $repo ('build\issue11-installer-' + [Guid]::NewGuid().ToString('N'))
$fixture = Join-Path $testRoot 'game'
$testRepo = Join-Path $testRoot 'repo'
$testTools = Join-Path $testRepo 'tools\v0.10.4'
New-Item -ItemType Directory -Path $testTools -Force | Out-Null
Copy-Item -Path (Join-Path $PSScriptRoot '*.py') -Destination $testTools
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-raven-resident-partial-linearization-proof.ps1') -Destination $testTools
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'collect-raven-resident-partial-linearization-proof.ps1') -Destination $testTools
foreach ($relative in @('exec\wad\pc_le\r_ui.wad','exec\wad\pc_le\root.texpack',
    'exec\dc\pc_le\wad_r_ui.dcb','exec\dc\pc_le\mapmaster.dcb','exec\boot-options.json',
    'exec\patch\pc_le\completionist_v104_raven_map.texpack')) {
    $destination = Join-Path $fixture $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
    Copy-Item -LiteralPath (Join-Path $GameRoot $relative) -Destination $destination
}

# Use real patcher and hashes. Fake only Git in fixture.
$testGitState = @{ Fail = ''; Repo = $testRepo; HeadReport = $null; StagedReport = $null; Calls = [Collections.Generic.List[string]]::new() }
function git {
    $testGitState.Calls.Add(($args -join ' '))
    $global:LASTEXITCODE = 0
    if ($args -contains '--show-current') { return 'feat/v0.10.4-all-ravens' }
    if ($args -contains '--quiet') { $global:LASTEXITCODE = 1 }
    if ($testGitState.Fail -and $args -contains $testGitState.Fail) { $global:LASTEXITCODE = 1 }
    $reportArg = [string]$args[-1]
    if ($reportArg -like '*-install.json') {
        if ($args -contains 'add') { $testGitState.StagedReport = Get-Content -LiteralPath (Join-Path $testGitState.Repo $reportArg) -Raw | ConvertFrom-Json }
        if ($args -contains 'commit' -and $global:LASTEXITCODE -eq 0) { $testGitState.HeadReport = $testGitState.StagedReport }
    }
}
function Assert-True($Value, [string]$Message) { if (-not $Value) { throw $Message } }
function Get-FixtureHash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }

$savedLocalAppData = $env:LOCALAPPDATA
$env:LOCALAPPDATA = Join-Path $testRoot 'localappdata'
$stateRoot = Join-Path $env:LOCALAPPDATA 'CompletionistMap\state'
foreach ($name in @('texpack-userhash-binding','artwork-patch-loading','artwork-layer')) {
    $dir = Join-Path $stateRoot ('v0.10.4-raven-' + $name)
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    [IO.File]::WriteAllText((Join-Path $dir 'active.json'), '{}')
}
$state = Join-Path $stateRoot 'v0.10.4-raven-resident-partial-linearization'
$active = Join-Path $state 'active.json'
$wad = Join-Path $fixture 'exec\wad\pc_le\r_ui.wad'
$baseHash = Get-FixtureHash $wad
$installer = Join-Path $testTools 'install-raven-resident-partial-linearization-proof.ps1'
$report = Join-Path $testRepo 'archive\field-logs\completionist-v104-raven-resident-partial-linearization-install.json'
try {
    & $installer -GameRoot $fixture
    Assert-True ((Get-FixtureHash $wad) -ne $baseHash) 'Install did not change fixture WAD.'
    Assert-True (Test-Path -LiteralPath $active) 'Install lacks active manifest.'
    $installedHash = Get-FixtureHash $wad
    & (Join-Path $testTools 'collect-raven-resident-partial-linearization-proof.ps1') -GameRoot $fixture
    Assert-True ((Get-FixtureHash $wad) -eq $installedHash) 'Collector changed WAD.'
    $backup = Join-Path $state 'r_ui.wad.before'
    $goodBackup = Join-Path $state 'r_ui.wad.known-good'
    Copy-Item -LiteralPath $backup -Destination $goodBackup
    [IO.File]::WriteAllText($backup, 'bad backup')
    $refused = $false
    try { & $installer -GameRoot $fixture -Mode Remove } catch { $refused = $_.Exception.Message -match 'Backup is not' }
    Assert-True $refused 'Remove accepted corrupt backup.'
    Assert-True ((Get-FixtureHash $wad) -eq $installedHash) 'Corrupt backup touched WAD.'
    Copy-Item -LiteralPath $goodBackup -Destination $backup -Force
    & $installer -GameRoot $fixture -Mode Remove
    Assert-True ((Get-FixtureHash $wad) -eq $baseHash) 'Remove failed to restore base.'

    $other = Join-Path $stateRoot 'v0.10.4-raven-resident-other\active.json'
    New-Item -ItemType Directory -Force -Path (Split-Path $other -Parent) | Out-Null
    [IO.File]::WriteAllText($other, '{}')
    $refused = $false
    try { & $installer -GameRoot $fixture } catch { $refused = $_.Exception.Message -match 'Resident proof active' }
    Assert-True $refused 'Install stacked resident proof.'
    Move-Item -LiteralPath $other -Destination ($other + '.removed')

    foreach ($failure in @('commit', 'push')) {
        $testGitState.Fail = $failure
        $refused = $false
        try { & $installer -GameRoot $fixture } catch { $refused = $_.Exception.Message -match $failure }
        Assert-True $refused "Expected $failure failure."
        Assert-True ((Get-FixtureHash $wad) -eq $baseHash) "$failure failure did not restore WAD."
        Assert-True (-not (Test-Path -LiteralPath $active)) "$failure failure left active manifest."
        $capture = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
        Assert-True ($capture.installed_into_game -eq $false) "$failure failure left success report."
        Assert-True ($testGitState.StagedReport.installed_into_game -eq $false) "$failure left false report staged."
        if ($failure -eq 'push') { Assert-True ($testGitState.HeadReport.installed_into_game -eq $false) 'Push failure left false report committed.' }
    }
    Assert-True (@($testGitState.Calls | Where-Object { $_ -match '^add ' -and $_ -notmatch '^add (?:-- )?archive/field-logs/completionist-v104-raven-resident-partial-linearization-(install.json|runtime.txt)$' }).Count -eq 0) 'Git staged unrelated files.'
    Assert-True ((Get-FixtureHash (Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad')) -eq $baseHash) 'Live WAD changed.'
    Write-Information -InformationAction Continue 'PASS: install, collector, corrupt backup, remove, proof conflict, commit rollback, push rollback.'
    Write-Information -InformationAction Continue "Fixture kept: $testRoot"
}
finally {
    $env:LOCALAPPDATA = $savedLocalAppData
}
