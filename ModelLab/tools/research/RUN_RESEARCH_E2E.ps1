$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = (Resolve-Path (Join-Path $here '..\..')).Path
Set-Location $root
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
$out = Join-Path $root 'runtime\research_e2e'
Write-Host 'MAX Research E2E - E2E_WORKFLOW_TEST_V1'
Write-Host 'Synthetic sandbox only - NOT production scientific evidence.'
& $python -m research.research_e2e --out $out --rows 4200
$rc = $LASTEXITCODE
Write-Host "Diagnostic evidence root: $(Join-Path $out 'diagnostic_evidence')"
if ($rc -ne 0) { exit $rc }
Write-Host "E2E PASS. Evidence: $out"
