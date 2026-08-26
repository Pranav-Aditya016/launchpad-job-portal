"""Freshersworld (freshersworld.com) — India entry-level/fresher job board.

SELECTORS ARE UNVERIFIED GUESSES — see `portal_naukri.py`'s header for why.
"""

from __future__ import annotations

from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers.portal_common import scrape_search_results
from app.sources.registry import register

SEARCH_URL_TEMPLATE = "https://www.freshersworld.com/jobs/jobsearch/{query}"


@register
class FreshersworldSource:
    meta = SourceMeta(
        key="freshersworld",
        label="Freshersworld",
        kind=SourceKind.PORTAL,
        regions=("in",),
        requires_login=True,
        login_url="https://www.freshersworld.com/login",
        logged_in_probe="https://www.freshersworld.com/member/dashboard",
        logged_in_selector=".member-name",
        rate_limit_s=3.0,
        daily_cap=200,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        return await scrape_search_results(
            ctx,
            portal=self.meta.key,
            search_url_template=SEARCH_URL_TEMPLATE,
            results_selector=".job-container",
            title_selector=".latest-jobs-title",
            link_selector=".latest-jobs-title a",
            company_selector=".company-name",
            location_selector=".job-location",
            region="in",
        )
