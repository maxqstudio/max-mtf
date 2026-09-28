$ErrorActionPreference = 'Stop'
$dstRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$parent = Split-Path -Parent $dstRoot
$srcRoot = Join-Path $parent 'CPMF_v0_7_1_R2'
if (-not (Test-Path $srcRoot)) { throw "Source v0.7.1 R2 tidak ditemukan sebagai sibling: $srcRoot" }
$srcLab = Join-Path $srcRoot 'ModelLab'
$dstLab = Join-Path $dstRoot 'ModelLab'
foreach ($name in @('runs','governance','factory_runs','.ui_cache')) {
    $src = Join-Path $srcLab $name; $dst = Join-Path $dstLab $name
    if (Test-Path $src) {
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force
        Write-Host "Migrated $name"
    }
}
$jobDir = Join-Path $dstLab 'factory_runs\_jobs'
if (Test-Path $jobDir) {
    Get-ChildItem $jobDir -Filter 'JOB_*.json' -File | Where-Object { $_.Name -notlike '*.candidates.json' -and $_.Name -notlike '*.heartbeat.json' } | ForEach-Object {
        try {
            $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
            foreach ($field in @('config_path','dataset','factory_dir')) {
                $v = [string]$j.payload.$field
                if ($v -and $v.StartsWith($srcRoot, [System.StringComparison]::OrdinalIgnoreCase)) { $j.payload.$field = $dstRoot + $v.Substring($srcRoot.Length) }
            }
            $j | ConvertTo-Json -Depth 64 | Set-Content $_.FullName -Encoding UTF8
        } catch { Write-Warning "Job payload path tidak dapat direbase: $($_.FullName) · $($_.Exception.Message)" }
    }
}
Write-Host 'Lineage/runtime migration v0.7.1 R2 -> v0.7.1 R3 selesai.'
Write-Host 'Settings/API tetap memakai %LOCALAPPDATA%\ComplexPolicy\ModelLab dan tidak perlu dimigrasikan.'
