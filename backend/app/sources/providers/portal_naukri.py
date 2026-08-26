"""Naukri (naukri.com) — India's largest general job board. Login-gated.

SELECTORS ARE UNVERIFIED GUESSES. This adapter cannot be logged in and
exercised live by the agent that wrote it (spec §6.2/§6.3: only the user ever
holds naukri credentials), so every selector below is a best-effort read of
Naukri's public-facing markup patterns, not a confirmed-live one. If results
come back empty, `portal_common.scrape_search_results` will warn loudly
rather than fail silently — treat that warning as "go re-inspect the DOM,"
not as "no jobs today."
"""

from __future__ import annotations

from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers.portal_common import scrape_search_results
from app.sources.registry import register

SEARCH_URL_TEMPLATE = "https://www.naukri.com/{query}-jobs"


@register
class NaukriSource:
    meta = SourceMeta(
        key="naukri",
        label="Naukri",
        kind=SourceKind.PORTAL,
        regions=("in",),
        requires_login=True,
        login_url="https://www.naukri.com/nlogin/login",
        logged_in_probe="https://www.naukri.com/mnjuser/homepage",
        logged_in_selector="[data-test='profile-name']",
        rate_limit_s=4.0,
        daily_cap=200,
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        return await scrape_search_results(
            ctx,
            portal=self.meta.key,
            search_url_template=SEARCH_URL_TEMPLATE,
            results_selector=".srp-jobtuple-wrapper",
            title_selector="a.title",
            link_selector="a.title",
            company_selector=".comp-name",
            location_selector=".locWdth",
            region="in",
        )
