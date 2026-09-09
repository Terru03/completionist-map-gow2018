param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $Python) { throw 'Python 3 is required.' }

$Input = Join-Path $RepoRoot 'build\v0.10.4-raven-inworld-trace\inworld-resource-trace.json'
$Output = Join-Path $RepoRoot 'build\v0.10.4-raven-inworld-trace\inworld-resource-topology-summary.json'
$Script = Join-Path $PSScriptRoot 'summarize-raven-inworld-resource-trace.py'

if (-not (Test-Path -LiteralPath $Input -PathType Leaf)) {
    throw "Missing prior trace report: $Input. Run run-raven-inworld-resource-trace.ps1 first."
}
if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) { throw "Missing summarizer: $Script" }

& $Python.Source $Script --input $Input --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Raven in-world topology summarizer failed.' }

Write-Host ''
Write-Host 'RAVEN_INWORLD_RESOURCE_TOPOLOGY_SUMMARY_COMPLETE'
Write-Host "  report: $Output"
Write-Host '  game files written: false'
