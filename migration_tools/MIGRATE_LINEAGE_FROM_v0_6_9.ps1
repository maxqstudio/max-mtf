$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Parent = Split-Path -Parent $Here
$Old = Join-Path $Parent "CPMF_v0_6_9"
if (-not (Test-Path $Old)) { throw "Sibling CPMF_v0_6_9 not found: $Old" }
foreach ($rel in @("ModelLab\runs", "ModelLab\governance", "ModelLab\factory_runs")) {
  $src = Join-Path $Old $rel
  $dst = Join-Path $Here $rel
  if (Test-Path $src) {
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Copy-Item -Path (Join-Path $src "*") -Destination $dst -Recurse -Force
    Write-Host "Migrated $rel"
  }
}
Write-Host "Lineage migration from v0.6.9 complete."
Write-Host "User settings/API/chat do not need migration; they remain under %LOCALAPPDATA%\ComplexPolicy\ModelLab."
