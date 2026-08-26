"""Wellfound (wellfound.com, formerly AngelList Talent) — startup jobs, global.

SELECTORS ARE UNVERIFIED GUESSES — see `portal_naukri.py`'s header for why.
"""

from __future__ import annotations

from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers.portal_common import scrape_search_results
from app.sources.registry import register

SEARCH_URL_TEMPLATE = "https://wellfound.com/jobs?query={query}"


@register
class WellfoundSource:
    meta = SourceMeta(
        key="wellfound",
        label="Wellfound",
        kind=SourceKind.PORTAL,
        regions=("global",),
        requires_login=True,
        login_url="https://wellfound.com/login",
        logged_in_probe="https://wellfound.com/jobs",
        logged_in_selector="[data-test='NavProfileMenu']",
        rate_limit_s=4.0,
        daily_cap=150,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        return await scrape_search_results(
            ctx,
            portal=self.meta.key,
            search_url_template=SEARCH_URL_TEMPLATE,
            results_selector=".job-listing-card",
            title_selector=".job-title",
            link_selector="a",
            company_selector=".startup-link",
            location_selector=".job-location",
            region="global",
        )
