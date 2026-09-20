[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside repository.'}
Set-Location $RepoRoot
$Tool=Join-Path $RepoRoot 'tools\v0.10.5\build-raven-serialized-gameobject-identities.py'
$Catalogue=Join-Path $RepoRoot 'catalogue\odins-ravens.json'
$Out=Join-Path $RepoRoot 'catalogue\odins-ravens-gameobject-identities.json'
$Text=Join-Path $RepoRoot 'archive\field-logs\source-scans\raven-serialized-gameobject-identities-latest.txt'
$branch=(& git branch --show-current).Trim()
if($branch-ne $ExpectedBranch){throw "Wrong branch '$branch'; expected '$ExpectedBranch'."}
$python=Get-Command python -ErrorAction SilentlyContinue
if(-not $python){throw 'python.exe not found in PATH.'}
New-Item -ItemType Directory -Force -Path (Split-Path $Text -Parent)|Out-Null
& $python.Source $Tool --catalogue $Catalogue --output $Out --text $Text
if($LASTEXITCODE-ne 0){throw 'Raven GameObject identity generation failed.'}
& git add -- 'catalogue/odins-ravens-gameobject-identities.json' 'archive/field-logs/source-scans/raven-serialized-gameobject-identities-latest.txt'
if($LASTEXITCODE-ne 0){throw 'git add failed.'}
& git commit -m 'research(v0.10.5): generate all Raven serialized GameObject identities'
if($LASTEXITCODE-ne 0){throw 'git commit failed.'}
& git push origin $ExpectedBranch
if($LASTEXITCODE-ne 0){throw 'git push failed.'}
Write-Host "RAVEN_SERIALIZED_GAMEOBJECT_IDENTITIES_PUSHED $((& git rev-parse HEAD).Trim())" -ForegroundColor Green
