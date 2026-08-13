<#
.SYNOPSIS
    Vendors santifer/career-ops into engine/career-ops and installs its
    dependencies without triggering the heavy Playwright browser download.

.DESCRIPTION
    Vendored commit (career-ops @ launchpad-v1 Task 4):
        f07fcad525e9ef2600b2203caae8dd05fa181b20

    career-ops' zero-LLM ATS scanner (scan-ats-full.mjs) is pure HTTP/JSON
    and does NOT need a browser unless you pass --liveness. Its package.json
    "postinstall" script runs `npx playwright install chromium --with-deps`
    unconditionally, so a plain `npm install` would pull down a full Chromium
    binary just to run a scanner that never launches one. `--ignore-scripts`
    skips that postinstall hook entirely.

    Run this from the repository root:
        pwsh -File scripts/setup-engine.ps1

.NOTES
    Requires Node.js >= 18 (career-ops' package.json "engines" field).
    This script only (re)creates engine/career-ops — it does not touch
    portals.yml or any other runtime config the scanner needs to actually
    scan (see engine/career-ops/templates/portals.example.yml).
#>

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$enginePath = Join-Path $repoRoot 'engine\career-ops'

Write-Host "Vendoring santifer/career-ops into $enginePath ..."

if (Test-Path $enginePath) {
    Write-Host "engine/career-ops already exists — skipping clone. Delete it first to re-vendor from scratch."
} else {
    # Step 1: shallow clone (depth 1 — we only need the current tree, not history)
    git clone --depth 1 https://github.com/santifer/career-ops.git $enginePath

    # Record the pinned commit before stripping .git (kept above in this file's header).
    $sha = git -C $enginePath rev-parse HEAD
    Write-Host "Vendored commit: $sha"

    # Step 2: strip the nested .git dir so it vendors as plain files, not a
    # git submodule / gitlink, inside this repo.
    Remove-Item -Recurse -Force (Join-Path $enginePath '.git')
}

# Step 3: install dependencies WITHOUT running postinstall (no Playwright
# browser download — the scanner is pure HTTP/JSON and doesn't need one
# unless you pass --liveness).
Push-Location $enginePath
try {
    npm install --ignore-scripts
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Done. Verify with:"
Write-Host "  cd engine/career-ops"
Write-Host "  node scan-ats-full.mjs --help"
Write-Host ""
Write-Host "To actually run a scan you first need a portals.yml (the scanner reads"
Write-Host "its title_filter/location_filter from it even for the reverse ATS scan):"
Write-Host "  cp engine/career-ops/templates/portals.example.yml engine/career-ops/portals.yml"
