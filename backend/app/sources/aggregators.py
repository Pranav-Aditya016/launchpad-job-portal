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

_ENDPOINTS = {
    "remotive":  ("https://remotive.com/api/remote-jobs", parse_remotive, "dict"),
    "arbeitnow": ("https://www.arbeitnow.com/api/job-board-api", parse_arbeitnow, "dict"),
    "remoteok":  ("https://remoteok.com/api", parse_remoteok, "list"),
    "jobicy":    ("https://jobicy.com/api/v2/remote-jobs?count=50", parse_jobicy, "dict"),
    "themuse":   ("https://www.themuse.com/api/public/jobs?level=Entry%20Level&page=0", parse_themuse, "dict"),
}
PROVIDERS = {k: v[1] for k, v in _ENDPOINTS.items()}

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
    return experience_filter(jobs) if fresher_only else jobs
