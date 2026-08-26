"""Cutshort (cutshort.io) — India tech-hiring portal. Login-gated.

SELECTORS ARE UNVERIFIED GUESSES — see `portal_naukri.py`'s header for why.
"""

from __future__ import annotations

from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers.portal_common import scrape_search_results
from app.sources.registry import register

SEARCH_URL_TEMPLATE = "https://cutshort.io/candidate/matches?q={query}"


@register
class CutshortSource:
    meta = SourceMeta(
        key="cutshort",
        label="Cutshort",
        kind=SourceKind.PORTAL,
        regions=("in",),
        requires_login=True,
        login_url="https://cutshort.io/login",
        logged_in_probe="https://cutshort.io/candidate/matches",
        logged_in_selector=".user-avatar",
        rate_limit_s=4.0,
        daily_cap=150,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        return await scrape_search_results(
            ctx,
            portal=self.meta.key,
            search_url_template=SEARCH_URL_TEMPLATE,
            results_selector=".job-card",
            title_selector=".job-title",
            link_selector="a.job-link",
            company_selector=".company-name",
            location_selector=".job-location",
            region="in",
        )
