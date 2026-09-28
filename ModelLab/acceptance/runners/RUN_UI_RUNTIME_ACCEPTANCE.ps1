$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $root
$Host.UI.RawUI.WindowTitle = 'Max Research Agent - UI Runtime Acceptance'

Write-Host '============================================================'
Write-Host 'MAX RESEARCH AGENT - REAL STREAMLIT UI RUNTIME ACCEPTANCE'
Write-Host '============================================================'
Write-Host 'This does NOT start research, place trades, compile MT5, or call an LLM.'
Write-Host 'It uses isolated temporary settings and a non-sending mock chat model.'
Write-Host ''

$runnerModule = 'acceptance.runners.ui_runtime_acceptance_bootstrap'
$python = Get-Command python -ErrorAction SilentlyContinue
$py = Get-Command py -ErrorAction SilentlyContinue

if ($python) {
    & $python.Source -m $runnerModule
    $rc = $LASTEXITCODE
} elseif ($py) {
    & $py.Source -m $runnerModule
    $rc = $LASTEXITCODE
} else {
    Write-Host '[FAIL] Python bootstrap tidak ditemukan. Install Python launcher atau Python 3.12, lalu ulangi.' -ForegroundColor Red
    $rc = 103
}

Write-Host ''
if ($rc -eq 0) {
    Write-Host '[PASS] Real Streamlit UI runtime acceptance PASS.' -ForegroundColor Green
} else {
    Write-Host "[FAIL] UI runtime acceptance exit code $rc." -ForegroundColor Red
}
Write-Host "Evidence: $root\evidence\ui\runtime\runtime_ui_acceptance\UI_RUNTIME_ACCEPTANCE_EVIDENCE.zip"
Write-Host "Report  : $root\evidence\ui\runtime\runtime_ui_acceptance\RUNTIME_UI_ACCEPTANCE.json"
exit $rc
