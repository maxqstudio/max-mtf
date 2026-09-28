param([string]$Source = "..\CPMF_v0_7_0")
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Src = (Resolve-Path (Join-Path $Here $Source)).Path
$Dst = $Here
foreach ($rel in @("ModelLab\runs","ModelLab\governance","ModelLab\factory_runs")) {
  $from = Join-Path $Src $rel
  $to = Join-Path $Dst $rel
  if (Test-Path $from) {
    New-Item -ItemType Directory -Force -Path $to | Out-Null
    Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force
    Write-Host "Migrated $rel"
  }
}
Write-Host "Settings/API are external in %LOCALAPPDATA%\ComplexPolicy\ModelLab and are not copied."
