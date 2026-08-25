# Seeds launchpad_data with shaped sample records (jobs.json, queue.json,
# runs/runs.json) so Track E can build the UI against non-empty, REAL API
# responses instead of hand-rolled mocks.
#
# Safety model: the real jobs.json is backed up to jobs.json.bak before being
# overwritten with demo data. To make re-running this safe, a seed refuses to
# run while a .bak already exists (that means a previous seed was never
# restored, and demo data must not be allowed to overwrite the only surviving
# copy of the real file). Run with -Restore to put the real jobs.json back
# and remove the demo queue.json / runs/runs.json this script created. This
# script does not touch profile.json at all.
param([switch]$Restore)

$ErrorActionPreference = "Stop"
$data = Join-Path $PSScriptRoot "..\launchpad_data"
New-Item -ItemType Directory -Force -Path $data | Out-Null

$jobsPath  = Join-Path $data "jobs.json"
$backupPath = "$jobsPath.bak"
$queuePath = Join-Path $data "queue.json"
$runsPath  = Join-Path $data "runs\runs.json"

if ($Restore) {
    if (-not (Test-Path $backupPath)) {
        Write-Host "No jobs.json.bak found in $data — nothing to restore."
        exit 0
    }
    Move-Item $backupPath $jobsPath -Force
    $removed = @()
    if (Test-Path $queuePath) { Remove-Item $queuePath -Force; $removed += "queue.json" }
    if (Test-Path $runsPath)  { Remove-Item $runsPath -Force;  $removed += "runs\runs.json" }
    Write-Host "Restored jobs.json from jobs.json.bak."
    if ($removed.Count -gt 0) {
        Write-Host ("Removed demo files: " + ($removed -join ", "))
    } else {
        Write-Host "No demo queue.json / runs\runs.json were present to remove."
    }
    exit 0
}

if (Test-Path $backupPath) {
    Write-Host "Refusing to seed: $backupPath already exists."
    Write-Host "This means a previous seed was never restored — jobs.json.bak is the only surviving copy of the real data that was backed up before it."
    Write-Host "Run 'pwsh scripts/seed-demo-data.ps1 -Restore' first, then re-run this script."
    exit 1
}

$jobs = @(
  @{ id="demo0001"; source="ats:greenhouse"; company="Databricks"; title="Software Engineer, New Grad";
     location="Bengaluru, IN"; url="https://example.invalid/1"; description="Demo posting.";
     posted="2026-08-25"; region="in"; first_seen="2026-08-26T09:00:00" },
  @{ id="demo0002"; source="naukri"; company="Zalando"; title="Junior Backend Engineer";
     location="Berlin, DE"; url="https://example.invalid/2"; description="Demo posting.";
     posted="2026-08-24"; region="de"; first_seen="2026-08-26T09:00:00" }
)
$queue = @(
  @{ job_id="demo0001"; state="ready";    score=91.0; prepared_at=$null; submitted_at=$null; cv_pdf=$null; notes="" },
  @{ job_id="demo0002"; state="prepared"; score=84.5; prepared_at="2026-08-26T09:05:00"; submitted_at=$null; cv_pdf=$null; notes="Form filled, awaiting your review." }
)
$runs = @(
  @{ id="demorun1"; started="2026-08-26T09:00:00"; finished="2026-08-26T09:04:12"; trigger="scheduled";
     per_source=@{ "ats:greenhouse"=40; "naukri"=12 }; warnings=@("linkedin: disabled by default");
     evaluated=25; tailored=6; partial=$false }
)

if (Test-Path $jobsPath) { Copy-Item $jobsPath $backupPath -Force }
# -AsArray: ConvertTo-Json collapses a single-element array into a bare JSON
# object instead of a [ ]-wrapped array, which would break store.py's
# load_runs()/load_queue() (they slice/iterate the parsed JSON as a list).
# Forcing an array keeps this correct at 1 element as well as N.
$jobs  | ConvertTo-Json -Depth 6 -AsArray | Set-Content -Encoding utf8 $jobsPath
$queue | ConvertTo-Json -Depth 6 -AsArray | Set-Content -Encoding utf8 $queuePath
New-Item -ItemType Directory -Force -Path (Join-Path $data "runs") | Out-Null
$runs  | ConvertTo-Json -Depth 6 -AsArray | Set-Content -Encoding utf8 $runsPath

Write-Host "Seeded demo data into $data (previous jobs.json backed up to jobs.json.bak)."
Write-Host "Run 'pwsh scripts/seed-demo-data.ps1 -Restore' to put the real jobs.json back."
