# Seeds launchpad_data with shaped sample records so Track E can build the UI
# against non-empty, REAL API responses instead of hand-rolled mocks.
# Safe: writes only into launchpad_data (gitignored) and refuses to clobber
# an existing profile.json.
$ErrorActionPreference = "Stop"
$data = Join-Path $PSScriptRoot "..\launchpad_data"
New-Item -ItemType Directory -Force -Path $data | Out-Null

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

$jobsPath = Join-Path $data "jobs.json"
if (Test-Path $jobsPath) { Copy-Item $jobsPath "$jobsPath.bak" -Force }
# -AsArray: ConvertTo-Json collapses a single-element array into a bare JSON
# object instead of a [ ]-wrapped array, which would break store.py's
# load_runs()/load_queue() (they slice/iterate the parsed JSON as a list).
# Forcing an array keeps this correct at 1 element as well as N.
$jobs  | ConvertTo-Json -Depth 6 -AsArray | Set-Content -Encoding utf8 $jobsPath
$queue | ConvertTo-Json -Depth 6 -AsArray | Set-Content -Encoding utf8 (Join-Path $data "queue.json")
New-Item -ItemType Directory -Force -Path (Join-Path $data "runs") | Out-Null
$runs  | ConvertTo-Json -Depth 6 -AsArray | Set-Content -Encoding utf8 (Join-Path $data "runs\runs.json")

Write-Host "Seeded demo data into $data (previous jobs.json backed up to jobs.json.bak)."
