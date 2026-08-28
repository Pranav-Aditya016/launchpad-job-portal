"""Websites the user adds themselves: "here's a link, scrape this too".

The registry covers the sites we ship adapters for. This covers everything
else — a company careers page, a niche board, a regional aggregator we've
never heard of. The user pastes a URL and it joins the scan.

Two things make this honest rather than a toy:

**Link filtering.** The v1 crawler treated every markdown link on a page as a
job, so "Privacy Policy" and "Log in" became postings. `looks_like_a_job`
below keeps that noise out, and a page with no job-shaped links yields nothing
rather than junk — an empty result the user can see beats fake rows they have
to sift.

**Provenance.** Every Job carries `source="custom:<id>"`, so the Sources page
can say exactly which of the user's sites a given posting came from.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from app import config as cfg
from app.models import Job, job_id
from app.store import _read_text, _write_atomic

_STORE = "custom_sources.json"

_MD_LINK = re.compile(r"\[([^\]]{1,200})\]\((\S+?)\)")

# A path that looks like it leads to one posting. Deliberately broad: a false
# negative loses a real job, a false positive costs one junk row the user can
# see and ignore.
_JOB_PATH = re.compile(
    r"(/jobs?/|/careers?/|/vacanc|/opening|/position|/stelle|/vagas|/emplo"
    r"|gh_jid=|/o/[a-z0-9-]{6,}|lever\.co/|greenhouse\.io/|ashbyhq\.com/"
    r"|smartrecruiters\.com/|workable\.com/|recruitee\.com/|myworkdayjobs\.com/)",
    re.I,
)

# Chrome that appears on careers pages and is never a posting.
_JUNK_TEXT = re.compile(
    r"^\s*(<|>|«|»|\d+|home|about( us)?|contact( us)?|privacy|cookies?|cookie settings"
    r"|terms|imprint|impressum|log ?in|sign ?in|sign ?up|register|search|menu|back"
    r"|next|previous|apply|apply now|read more|learn more|view all|all jobs|share"
    r"|linkedin|twitter|facebook|instagram|youtube|newsletter|blog|press|faq"
    r"|benefits|culture|life at .*|our team|meet the team)\s*$",
    re.I,
)

_JUNK_PATH = re.compile(
    r"(/privacy|/cookie|/terms|/imprint|/impressum|/legal|/login|/signin|/sign-in"
    r"|/register|/blog|/press|/news|/about|/contact|/faq|/benefits|/culture"
    r"|/newsletter|\.pdf$|\.jpg$|\.png$|^mailto:|^tel:)",
    re.I,
)


@dataclass
class CustomSite:
    id: str
    url: str
    label: str
    regions: list[str] = field(default_factory=lambda: ["global"])
    enabled: bool = True
    notes: str = ""

    # Written back after each scan so the UI can be honest about whether the
    # user's site is actually producing anything.
    last_status: str = ""      # "" | ok | empty | error
    last_jobs: int = 0
    last_detail: str = ""


def _path() -> "object":
    return cfg.DATA_DIR / _STORE


def _normalise(url: str) -> str:
    """Validate and canonicalise, or raise ValueError.

    Only http(s) — a `javascript:` or `file:` URL here would be pointed at a
    browser later, so this is a security boundary, not just tidiness.
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("a URL is required")
    if not re.match(r"^https?://", url, re.I):
        raise ValueError(
            f"{url!r} is not an http(s) URL — paste the full address, "
            "starting with https://"
        )
    parsed = urlparse(url)
    if not parsed.netloc or "." not in parsed.netloc:
        raise ValueError(f"{url!r} does not contain a valid domain")
    if parsed.scheme.lower() == "http":
        url = "https://" + url.split("://", 1)[1]
    return url.rstrip()


def _site_id(url: str) -> str:
    return hashlib.sha256(url.lower().encode()).hexdigest()[:12]


def load_all() -> list[CustomSite]:
    text = _read_text(_path())
    if text is None:
        return []
    try:
        raw = json.loads(text)
    except Exception:
        return []          # corrupt reads as absent, like every other store
    out = []
    for r in raw if isinstance(raw, list) else []:
        try:
            out.append(CustomSite(**r))
        except Exception:
            continue        # one bad record must not hide the rest
    return out


def _save_all(sites: list[CustomSite]) -> None:
    _write_atomic(_path(), json.dumps([asdict(s) for s in sites], indent=2))


def get(site_id: str) -> CustomSite | None:
    return next((s for s in load_all() if s.id == site_id), None)


def add(url: str, label: str = "", regions: list[str] | None = None,
        notes: str = "") -> CustomSite:
    """Add a site, or update it in place if the URL is already known."""
    url = _normalise(url)
    site = CustomSite(
        id=_site_id(url),
        url=url,
        label=(label or "").strip() or urlparse(url).netloc,
        regions=regions or ["global"],
        notes=notes,
    )
    sites = load_all()
    for i, existing in enumerate(sites):
        if existing.id == site.id:
            site.last_status = existing.last_status
            site.last_jobs = existing.last_jobs
            sites[i] = site
            break
    else:
        sites.append(site)
    _save_all(sites)
    return site


def remove(site_id: str) -> bool:
    sites = load_all()
    kept = [s for s in sites if s.id != site_id]
    if len(kept) == len(sites):
        return False
    _save_all(kept)
    return True


def set_enabled(site_id: str, enabled: bool) -> bool:
    sites = load_all()
    for s in sites:
        if s.id == site_id:
            s.enabled = bool(enabled)
            _save_all(sites)
            return True
    return False


def record_result(site_id: str, status: str, jobs: int, detail: str = "") -> None:
    """Remember how the last scan went, so the UI can show it."""
    sites = load_all()
    for s in sites:
        if s.id == site_id:
            s.last_status, s.last_jobs, s.last_detail = status, jobs, detail[:300]
            _save_all(sites)
            return


def looks_like_a_job(title: str, url: str) -> bool:
    """Is this link plausibly ONE job posting?"""
    title = (title or "").strip()
    if not title or len(title) > 160:
        return False
    if _JUNK_TEXT.match(title):
        return False
    if _JUNK_PATH.search(url):
        return False
    return bool(_JOB_PATH.search(url))


def jobs_from_markdown(md: str, base_url: str, company: str, source_key: str) -> list[Job]:
    """Job links from a rendered page, with the boilerplate filtered out."""
    seen: set[str] = set()
    jobs: list[Job] = []
    for title, href in _MD_LINK.findall(md or ""):
        url = urljoin(base_url, href.strip())
        if url in seen or not looks_like_a_job(title, url):
            continue
        seen.add(url)
        jobs.append(Job(
            id=job_id(source_key, company, url),
            source=source_key,
            company=company,
            title=" ".join(title.split()),
            url=url,
        ))
    return jobs


# A board URL is rarely one page. Following a handful keeps a paginated site
# from contributing only its first screen, without turning into a crawler.
MAX_PAGES = 5
_PAGE_PARAMS = ("page", "p", "pg", "offset", "start")


def page_urls(url: str, max_pages: int = MAX_PAGES) -> list[str]:
    """`url` plus the next few pages, if it carries a page parameter.

    Returns just the original when there is nothing to walk — guessing at
    pagination on a URL that has none would fetch the same page repeatedly.
    """
    parsed = urlparse(url)
    params = parse_qsl(parsed.query, keep_blank_values=True)
    key = next((k for k, _ in params if k.lower() in _PAGE_PARAMS), None)
    if key is None or max_pages <= 1:
        return [url]
    try:
        start = int(dict(params)[key])
    except (ValueError, KeyError):
        return [url]

    out = []
    for i in range(max_pages):
        page = [(k, str(start + i) if k == key else v) for k, v in params]
        out.append(urlunparse(parsed._replace(query=urlencode(page))))
    return out
