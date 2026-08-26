"""Internshala (internshala.com) — India internships and entry-level jobs.

SELECTORS ARE UNVERIFIED GUESSES — see `portal_naukri.py`'s header for why.
"""

from __future__ import annotations

from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers.portal_common import scrape_search_results
from app.sources.registry import register

SEARCH_URL_TEMPLATE = "https://internshala.com/internships/keywords-{query}"


@register
class InternshalaSource:
    meta = SourceMeta(
        key="internshala",
        label="Internshala",
        kind=SourceKind.PORTAL,
        regions=("in",),
        requires_login=True,
        login_url="https://internshala.com/login/student",
        logged_in_probe="https://internshala.com/student/dashboard",
        logged_in_selector=".user_name",
        rate_limit_s=3.0,
        daily_cap=200,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        return await scrape_search_results(
            ctx,
            portal=self.meta.key,
            search_url_template=SEARCH_URL_TEMPLATE,
            results_selector=".individual_internship",
            title_selector=".job-internship-name",
            link_selector=".job-internship-name a",
            company_selector=".company-name",
            location_selector=".locations",
            region="in",
        )
