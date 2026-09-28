$ErrorActionPreference = 'Stop'
$dstRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$parent = Split-Path -Parent $dstRoot
$srcRoot = Join-Path $parent 'CPMF_v0_7_1_R3'
if (-not (Test-Path $srcRoot)) { throw "Source v0.7.1 R3 tidak ditemukan sebagai sibling: $srcRoot" }
$srcLab = Join-Path $srcRoot 'ModelLab'
$archiveRoot = Join-Path $dstRoot 'legacy_v0_7_1_R3_readonly'
New-Item -ItemType Directory -Force -Path $archiveRoot | Out-Null
foreach ($name in @('runs','governance','factory_runs','.ui_cache')) {
    $src = Join-Path $srcLab $name
    $dst = Join-Path $archiveRoot $name
    if (Test-Path $src) {
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force
        Write-Host "Archived read-only lineage: $name"
    }
}
$notice = @'
CPMF v0.7.2 R1 changes research-kernel evaluation semantics.
Legacy v0.7.1 R3 Factory/checkpoint/global research memory is therefore archived for audit only.
It is intentionally NOT copied into active ModelLab\factory_runs and must not be resumed under v0.7.2 R1.
Start a NEW Factory so CPCV/hybrid OOF evidence is generated entirely under Research Kernel V2.
Settings/API remain persisted separately under %LOCALAPPDATA%\ComplexPolicy\ModelLab.
'@
Set-Content -Path (Join-Path $archiveRoot 'READ_ONLY_MIGRATION_NOTICE.txt') -Value $notice -Encoding UTF8
Write-Host 'Legacy v0.7.1 R3 evidence archived read-only. Active research lineage was NOT migrated.'
Write-Host 'Start a NEW Factory in v0.7.2 R1.'
