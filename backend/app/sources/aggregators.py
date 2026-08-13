import os
import re
import httpx
from app.models import Job, job_id

_TAG = re.compile(r"<[^>]+>")
def _clean(s): return _TAG.sub(" ", s or "").strip()

def parse_remotive(data: dict) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        url = j.get("url", "")
        out.append(Job(id=job_id("remotive", j.get("company_name",""), url),
            source="remotive", company=j.get("company_name",""), title=j.get("title",""),
            location=j.get("candidate_required_location",""), url=url,
            description=_clean(j.get("description","")), posted=j.get("publication_date")))
    return out

def parse_arbeitnow(data: dict) -> list[Job]:
    out = []
    for j in data.get("data", []):
        url = j.get("url", "")
        out.append(Job(id=job_id("arbeitnow", j.get("company_name",""), url),
            source="arbeitnow", company=j.get("company_name",""), title=j.get("title",""),
            location=j.get("location",""), url=url,
            description=_clean(j.get("description","")), posted=str(j.get("created_at",""))))
    return out

def parse_remoteok(data: list) -> list[Job]:
    out = []
    for j in data:
        # first element is legal metadata (has no "position"/"id" job fields)
        if not isinstance(j, dict) or not j.get("position"):
            continue
        url = j.get("url", "")
        out.append(Job(id=job_id("remoteok", j.get("company",""), url),
            source="remoteok", company=j.get("company",""), title=j.get("position",""),
            location=j.get("location",""), url=url,
            description=_clean(j.get("description","")), posted=j.get("date")))
    return out

def parse_jobicy(data: dict) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        url = j.get("url", "")
        out.append(Job(id=job_id("jobicy", j.get("companyName",""), url),
            source="jobicy", company=j.get("companyName",""), title=j.get("jobTitle",""),
            location=j.get("jobGeo",""), url=url,
            description=_clean(j.get("jobExcerpt","") or j.get("jobDescription","")),
            posted=j.get("pubDate")))
    return out

def parse_themuse(data: dict) -> list[Job]:
    out = []
    for j in data.get("results", []):
        url = (j.get("refs") or {}).get("landing_page", "")
        company = (j.get("company") or {}).get("name", "")
        locs = ", ".join(l.get("name","") for l in j.get("locations", []))
        out.append(Job(id=job_id("themuse", company, url), source="themuse",
            company=company, title=j.get("name",""), location=locs, url=url,
            description=_clean(j.get("contents","")), posted=j.get("publication_date")))
    return out

def parse_adzuna(data: dict, country: str) -> list[Job]:
    out = []
    for j in data.get("results", []):
        url = j.get("redirect_url", "")
        company = (j.get("company") or {}).get("display_name", "")
        loc = (j.get("location") or {}).get("display_name", "")
        out.append(Job(id=job_id("adzuna", company, url), source=f"adzuna-{country}",
            company=company, title=j.get("title",""), location=loc, url=url,
            description=_clean(j.get("description","")), posted=j.get("created")))
    return out

_ENDPOINTS = {
    "remotive":  ("https://remotive.com/api/remote-jobs", parse_remotive, "dict"),
    "arbeitnow": ("https://www.arbeitnow.com/api/job-board-api", parse_arbeitnow, "dict"),
    "remoteok":  ("https://remoteok.com/api", parse_remoteok, "list"),
    "jobicy":    ("https://jobicy.com/api/v2/remote-jobs?count=50", parse_jobicy, "dict"),
    "themuse":   ("https://www.themuse.com/api/public/jobs?level=Entry%20Level&page=0", parse_themuse, "dict"),
}
PROVIDERS = {k: v[1] for k, v in _ENDPOINTS.items()}

# India + Germany first: the user is an Indian citizen who also wants
# Germany/UK/US roles where visa sponsorship is realistically available.
ADZUNA_COUNTRIES = ["in", "de", "gb", "us"]

async def fetch_adzuna(client: httpx.AsyncClient, query: str = "", countries=None) -> list[Job]:
    # OPT-IN: Adzuna requires a free app_id/app_key (developer.adzuna.com). If
    # the env vars aren't set, we skip the call entirely rather than failing.
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []
    jobs: list[Job] = []
    for c in (countries or ADZUNA_COUNTRIES):
        url = (f"https://api.adzuna.com/v1/api/jobs/{c}/search/1"
               f"?app_id={app_id}&app_key={app_key}&results_per_page=50"
               f"&max_days_old=30&what={query or 'engineer'}")
        try:
            r = await client.get(url)
            r.raise_for_status()
            jobs.extend(parse_adzuna(r.json(), c))
        except Exception:
            continue  # per-source (per-country) non-fatal (spec §6)
    return jobs

# --- Curated niche crawl targets (used via crawl_adapter.fetch_jobs, opt-in
# through /scan's crawl_curated flag) --------------------------------------
#
# HONESTY: h1bvisajobs, TrueUp and Absolute Internship have no public API and
# are JS-heavy sites. crawl4ai's markdown-link extraction (crawl_adapter.py)
# is best-effort — it grabs every markdown link on the rendered page, so it
# can capture navigation/footer noise alongside real listings and may need
# per-site CSS selectors later for cleaner results. These three SUPPLEMENT —
# they do not replace — the reliable API providers above (career-ops ATS scan
# + Adzuna + the five remote aggregators). Absolute Internship in particular
# is a paid placement PROGRAM (the applicant pays a placement fee), not a
# standard job board, so real job yield from its listing page is expected to
# be low; it's included only because it's a named source in the brief.
CURATED_CRAWL_SOURCES = [
    {"company": "h1bvisajobs", "url": "https://www.h1bvisajobs.com/jobs",
     "sponsor_friendly": True},   # US roles from H1B-sponsoring employers
    {"company": "trueup",       "url": "https://www.trueup.io/jobs"},
    {"company": "absolute-internship", "url": "https://absoluteinternship.com/internships/"},
]
SPONSOR_FRIENDLY_SOURCES = {"h1bvisajobs"}

async def fetch_all(query: str = "", providers=None, fresher_only: bool = True) -> list[Job]:
    from app.sources.experience import experience_filter
    names = providers or list(_ENDPOINTS.keys())
    jobs: list[Job] = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "LaunchPad/1.0"}) as client:
        for name in names:
            if name not in _ENDPOINTS:
                continue
            url, parser, _ = _ENDPOINTS[name]
            if name == "remotive" and query:
                url = f"{url}?search={query}"
            try:
                r = await client.get(url)
                r.raise_for_status()
                jobs.extend(parser(r.json()))
            except Exception:
                continue  # per-source non-fatal (spec §6)
        jobs.extend(await fetch_adzuna(client, query))
    return experience_filter(jobs) if fresher_only else jobs
