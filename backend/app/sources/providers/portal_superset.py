"""Superset (joinsuperset.com) — India campus-recruitment portal.

SELECTORS ARE UNVERIFIED GUESSES — see `portal_naukri.py`'s header for why.
"""

from __future__ import annotations

from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers.portal_common import scrape_search_results
from app.sources.registry import register

SEARCH_URL_TEMPLATE = "https://app.joinsuperset.com/candidate/jobs?q={query}"


@register
class SupersetSource:
    meta = SourceMeta(
        key="superset",
        label="Superset",
        kind=SourceKind.PORTAL,
        regions=("in",),
        requires_login=True,
        login_url="https://app.joinsuperset.com/login",
        logged_in_probe="https://app.joinsuperset.com/dashboard",
        logged_in_selector="[data-testid='user-menu']",
        rate_limit_s=4.0,
        daily_cap=150,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        return await scrape_search_results(
            ctx,
            portal=self.meta.key,
            search_url_template=SEARCH_URL_TEMPLATE,
            results_selector="[data-testid='job-card']",
            title_selector="[data-testid='job-title']",
            link_selector="a",
            company_selector="[data-testid='company-name']",
            location_selector="[data-testid='job-location']",
            region="in",
        )
