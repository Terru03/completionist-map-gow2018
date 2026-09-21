[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

$ExpectedBranch='codex/all-ravens-release-candidate'
$RepoRoot=(& git rev-parse --show-toplevel 2>$null).Trim()
if([string]::IsNullOrWhiteSpace($RepoRoot)){throw 'Not inside repository.'}
Set-Location $RepoRoot

$branch=(& git branch --show-current).Trim()
if($branch-ne $ExpectedBranch){throw "Wrong branch '$branch'; expected '$ExpectedBranch'."}

$Tool=Join-Path $RepoRoot 'tools\v0.10.5\resolve-raven-nested-container-identities-static.py'
$Catalogue=Join-Path $RepoRoot 'catalogue\odins-ravens.json'
$Replay=Join-Path $RepoRoot 'archive\field-logs\runtime-captures\staged-wad-bitstream-raven-20260921-060345-c2c9bcc1\replay-report.json'
$Stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$OutDir=Join-Path $RepoRoot "archive\field-logs\source-scans\raven-nested-container-identities-static-$Stamp"
$Json=Join-Path $OutDir 'report.json'
$Text=Join-Path $OutDir 'report.txt'
$Console=Join-Path $OutDir 'console-log.txt'

New-Item -ItemType Directory -Force -Path $OutDir|Out-Null
$python=Get-Command python -ErrorAction SilentlyContinue
if(-not $python){throw 'python.exe not found in PATH.'}

& $python.Source $Tool --catalogue $Catalogue --replay-report $Replay --output-json $Json --output-text $Text 2>&1 |
    Tee-Object -FilePath $Console
if($LASTEXITCODE-ne 0){throw 'Nested Raven identity static solver failed.'}

$rel=$OutDir.Substring($RepoRoot.Length+1).Replace('\','/')
& git add -- $rel 'tools/v0.10.5/resolve-raven-nested-container-identities-static.py' 'tools/v0.10.5/resolve-raven-nested-container-identities-static-and-push.ps1'
if($LASTEXITCODE-ne 0){throw 'git add failed.'}
& git commit -m 'research(v0.10.5): resolve nested Raven identity elements'
if($LASTEXITCODE-ne 0){throw 'git commit failed.'}
& git push origin $ExpectedBranch
if($LASTEXITCODE-ne 0){throw 'git push failed.'}
Write-Host "RAVEN_NESTED_CONTAINER_IDENTITY_PUSHED $((& git rev-parse HEAD).Trim()) $rel" -ForegroundColor Green
