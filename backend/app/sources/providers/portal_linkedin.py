"""LinkedIn (linkedin.com) — explicitly best-effort, spec §6.2.

LinkedIn runs the most aggressive anti-automation of any target this project
touches. This adapter is **disabled by default**, rate-limited to human pace,
capped low per day, and carries a plain-language warning on its UI card. We
do not evade detection: if LinkedIn blocks us, `session.verify` reports
`blocked` and the scheduler skips it — see spec §6.2/§7. No amount of
selector polish changes that policy.

SELECTORS ARE UNVERIFIED GUESSES — see `portal_naukri.py`'s header for why;
LinkedIn's DOM is also the most likely of any target here to have drifted
from whatever this adapter was written against.
"""

from __future__ import annotations

from app.models import Job
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers.portal_common import scrape_search_results
from app.sources.registry import register

SEARCH_URL_TEMPLATE = "https://www.linkedin.com/jobs/search/?keywords={query}"


@register
class LinkedInSource:
    meta = SourceMeta(
        key="linkedin",
        label="LinkedIn",
        kind=SourceKind.PORTAL,
        regions=("global",),
        requires_login=True,
        login_url="https://www.linkedin.com/login",
        logged_in_probe="https://www.linkedin.com/feed/",
        logged_in_selector="#global-nav",
        rate_limit_s=8.0,
        daily_cap=60,
        enabled_by_default=False,
        warning=(
            "LinkedIn aggressively detects automated browsing. Heavy or frequent "
            "use of this connection can get your account temporarily restricted "
            "or permanently banned. Off by default — enable only if you accept "
            "that risk, and expect it to stop working (status: blocked) the "
            "moment LinkedIn notices."
        ),
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        return await scrape_search_results(
            ctx,
            portal=self.meta.key,
            search_url_template=SEARCH_URL_TEMPLATE,
            results_selector=".job-card-container",
            title_selector=".job-card-list__title",
            link_selector="a.job-card-list__title",
            company_selector=".job-card-container__company-name",
            location_selector=".job-card-container__metadata-item",
            region="global",
            max_per_query=15,  # extra-conservative: this source is rate_limit_s=8, daily_cap=60
        )
