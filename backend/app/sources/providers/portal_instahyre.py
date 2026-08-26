"""Instahyre (instahyre.com) — India tech-hiring portal. Login-gated.

SELECTORS ARE UNVERIFIED GUESSES — see `portal_naukri.py`'s header for why.
"""

from __future__ import annotations

from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers.portal_common import scrape_search_results
from app.sources.registry import register

SEARCH_URL_TEMPLATE = "https://www.instahyre.com/candidate/opportunities/?q={query}"


@register
class InstahyreSource:
    meta = SourceMeta(
        key="instahyre",
        label="Instahyre",
        kind=SourceKind.PORTAL,
        regions=("in",),
        requires_login=True,
        login_url="https://www.instahyre.com/login/",
        logged_in_probe="https://www.instahyre.com/candidate/opportunities/",
        logged_in_selector=".candidate-name",
        rate_limit_s=4.0,
        daily_cap=150,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        return await scrape_search_results(
            ctx,
            portal=self.meta.key,
            search_url_template=SEARCH_URL_TEMPLATE,
            results_selector=".opportunity",
            title_selector=".opportunity-title",
            link_selector=".opportunity-title a",
            company_selector=".company-name",
            location_selector=".opportunity-location",
            region="in",
        )
