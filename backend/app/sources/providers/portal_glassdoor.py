"""Glassdoor (glassdoor.com) — same conservative treatment as LinkedIn, spec §6.2.

Disabled by default, rate-limited, capped low per day, with a plain-language
UI warning. We do not evade detection: if Glassdoor blocks us,
`session.verify` reports `blocked` and the scheduler skips it.

SELECTORS ARE UNVERIFIED GUESSES — see `portal_naukri.py`'s header for why.
"""

from __future__ import annotations

from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers.portal_common import scrape_search_results
from app.sources.registry import register

SEARCH_URL_TEMPLATE = "https://www.glassdoor.com/Job/jobs.htm?sc.keyword={query}"


@register
class GlassdoorSource:
    meta = SourceMeta(
        key="glassdoor",
        label="Glassdoor",
        kind=SourceKind.PORTAL,
        regions=("global",),
        requires_login=True,
        login_url="https://www.glassdoor.com/profile/login_input.htm",
        logged_in_probe="https://www.glassdoor.com/member/home/index.htm",
        logged_in_selector="[data-test='profile-nav']",
        rate_limit_s=6.0,
        daily_cap=100,
        enabled_by_default=False,
        warning=(
            "Glassdoor also detects and can restrict automated browsing. Off by "
            "default, rate-limited to a human-like pace when enabled. Expect it "
            "to stop working (status: blocked) rather than push through."
        ),
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        return await scrape_search_results(
            ctx,
            portal=self.meta.key,
            search_url_template=SEARCH_URL_TEMPLATE,
            results_selector="li[data-test='jobListing']",
            title_selector="[data-test='job-title']",
            link_selector="a[data-test='job-link']",
            company_selector="[data-test='employer-name']",
            location_selector="[data-test='emp-location']",
            region="global",
            max_per_query=20,
        )
