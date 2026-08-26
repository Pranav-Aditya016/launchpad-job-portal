"""Shared scraping helper for tier-3 login-gated portal adapters.

Every `portal_*.py` source in this package works the same way: get a page
bound to the portal's persistent login session (`ctx.open_page`), navigate to
a search-results URL built from the caller's queries, wait for the results
container, and pull (title, company, location, url) out of each result card.

The one rule every adapter must follow, learned the hard way (see the Track C
brief): **a selector that matches zero elements must warn loudly, never
return silently-empty results.** An empty list from a portal whose page
layout changed looks identical to "no matching jobs today" unless something
says otherwise — that ambiguity is what cost this project a day before.
"""

from __future__ import annotations

from urllib.parse import quote, urljoin

from app.models import Job
from app.sources.base import FetchContext, SourceUnavailable

MAX_QUERIES = 5
MAX_PER_QUERY = 30
NAV_TIMEOUT_MS = 25_000
RESULTS_TIMEOUT_MS = 12_000


async def scrape_search_results(
    ctx: FetchContext,
    *,
    portal: str,
    search_url_template: str,   # must contain one "{query}" placeholder
    results_selector: str,      # one element per job card
    title_selector: str,        # relative to a card
    link_selector: str,         # relative to a card; read via get_attribute("href")
    company_selector: str = "",
    location_selector: str = "",
    region: str = "global",
    max_per_query: int = MAX_PER_QUERY,
    results_timeout_ms: int = RESULTS_TIMEOUT_MS,
) -> list[Job]:
    """Scrape a logged-in portal's search results for every query in `ctx.queries`.

    Never returns silently on a zero-match selector — it calls `ctx.warn(...)`
    instead, so a portal redesign shows up as a warning on the scan run
    rather than as a quietly-empty source. This is deliberately distinct from
    a page that genuinely fails to load (network error, DNS failure, portal
    down): that gets its own "could not load results" warning. A page that
    loads fine but whose results selector finds nothing — whether because the
    query genuinely has zero hits or because the DOM has drifted — always
    goes through the zero-match path below, since from here the two look
    identical and both deserve a loud warning rather than a silent empty list.
    """
    try:
        page = await ctx.open_page(portal)
    except SourceUnavailable:
        raise
    except Exception as e:  # pragma: no cover - defensive, mirrors open_page's own guard
        raise SourceUnavailable(f"{portal}: could not open browser session ({e})") from e

    jobs: list[Job] = []
    queries = ctx.queries or [""]
    for query in queries[:MAX_QUERIES]:
        search_url = search_url_template.format(query=quote(query))
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        except Exception as e:
            ctx.warn(f"{portal}: could not load results for {query!r} ({e})")
            continue

        # A results selector that never appears is NOT a load failure — it's
        # either a genuine zero-result query or a layout change. Either way
        # `cards.count()` below reports 0 and we warn accordingly, so a
        # timeout here is swallowed rather than mis-reported as "could not
        # load results".
        try:
            await page.wait_for_selector(results_selector, timeout=results_timeout_ms)
        except Exception:
            pass

        cards = page.locator(results_selector)
        try:
            count = await cards.count()
        except Exception as e:
            ctx.warn(f"{portal}: results selector matched 0 elements ({e}); the page layout probably changed")
            continue

        if count == 0:
            ctx.warn(f"{portal}: results selector matched 0 elements; the page layout probably changed")
            continue

        for i in range(min(count, max_per_query)):
            job = await _extract_one(
                cards.nth(i), portal=portal, search_url=search_url, region=region,
                title_selector=title_selector, link_selector=link_selector,
                company_selector=company_selector, location_selector=location_selector,
            )
            if job is not None:
                jobs.append(job)

    return jobs


async def _extract_one(
    card, *, portal: str, search_url: str, region: str,
    title_selector: str, link_selector: str, company_selector: str, location_selector: str,
) -> Job | None:
    try:
        title = (await card.locator(title_selector).first.inner_text()).strip()
        href = await card.locator(link_selector).first.get_attribute("href")
    except Exception:
        return None
    if not title or not href:
        return None

    url = urljoin(search_url, href)

    company = ""
    if company_selector:
        with_ = card.locator(company_selector).first
        try:
            company = (await with_.inner_text()).strip()
        except Exception:
            company = ""

    location = ""
    if location_selector:
        loc_ = card.locator(location_selector).first
        try:
            location = (await loc_.inner_text()).strip()
        except Exception:
            location = ""

    return Job(
        id=f"{portal}:{url}", source=portal, company=company, title=title,
        location=location, url=url, region=region,
    )
