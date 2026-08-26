"""StepStone (stepstone.de) — Germany general job board. Login-gated.

SELECTORS ARE UNVERIFIED GUESSES — see `portal_naukri.py`'s header for why.
"""

from __future__ import annotations

from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers.portal_common import scrape_search_results
from app.sources.registry import register

SEARCH_URL_TEMPLATE = "https://www.stepstone.de/jobs/{query}"


@register
class StepStoneSource:
    meta = SourceMeta(
        key="stepstone",
        label="StepStone",
        kind=SourceKind.PORTAL,
        regions=("de",),
        requires_login=True,
        login_url="https://www.stepstone.de/login",
        logged_in_probe="https://www.stepstone.de/members/dashboard",
        logged_in_selector="[data-at='header-profile-menu']",
        rate_limit_s=4.0,
        daily_cap=200,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        return await scrape_search_results(
            ctx,
            portal=self.meta.key,
            search_url_template=SEARCH_URL_TEMPLATE,
            results_selector="article[data-at='job-item']",
            title_selector="[data-at='job-item-title']",
            link_selector="a[data-at='job-item-title']",
            company_selector="[data-at='job-item-company-name']",
            location_selector="[data-at='job-item-location']",
            region="de",
        )
