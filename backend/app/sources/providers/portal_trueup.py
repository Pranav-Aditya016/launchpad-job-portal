"""TrueUp (trueup.io) — tech-company job/salary aggregator, global.

SELECTORS ARE UNVERIFIED GUESSES — see `portal_naukri.py`'s header for why.
"""

from __future__ import annotations

from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers.portal_common import scrape_search_results
from app.sources.registry import register

SEARCH_URL_TEMPLATE = "https://www.trueup.io/jobs?q={query}"


@register
class TrueUpSource:
    meta = SourceMeta(
        key="trueup",
        label="TrueUp",
        kind=SourceKind.PORTAL,
        regions=("global",),
        requires_login=True,
        login_url="https://www.trueup.io/login",
        logged_in_probe="https://www.trueup.io/jobs",
        logged_in_selector=".user-menu",
        rate_limit_s=4.0,
        daily_cap=150,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        return await scrape_search_results(
            ctx,
            portal=self.meta.key,
            search_url_template=SEARCH_URL_TEMPLATE,
            results_selector=".job-card",
            title_selector=".job-card-title",
            link_selector="a",
            company_selector=".job-card-company",
            location_selector=".job-card-location",
            region="global",
        )
