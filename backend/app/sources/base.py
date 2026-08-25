"""The one interface every job source implements.

Deliberately dependency-free: no httpx client construction, no Playwright import,
no store access. That is what lets tracks B, C and D develop against it in
parallel without importing each other's work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from app.models import Job, Profile


class SourceUnavailable(RuntimeError):
    """A source cannot run right now (no session, no browser, capped out).

    Distinct from a bug: the scheduler catches this, records a warning against the
    run, and carries on with every other source (spec §7).
    """


class SourceKind(str, Enum):
    PUBLIC = "public"   # tier 1 — open HTTP/JSON, no auth
    ATS = "ats"         # tier 2 — a company career site on a known ATS
    PORTAL = "portal"   # tier 3 — needs the user's own login session
    CRAWL = "crawl"     # curated page scrape


@dataclass(frozen=True)
class SourceMeta:
    """Everything the scheduler and UI need to know without running the source."""

    key: str                        # stable unique id, e.g. "naukri", "ats:greenhouse"
    label: str                      # display name
    kind: SourceKind
    regions: tuple[str, ...] = ("global",)
    requires_login: bool = False

    # tier 3 only — how the user connects, and how we later prove the session lives
    login_url: str = ""
    logged_in_probe: str = ""       # a URL only reachable when logged in
    logged_in_selector: str = ""    # CSS present only when logged in

    # Courtesy + account safety (spec §12.5). Enforced by the scheduler, not by
    # each adapter, so a careless adapter cannot hammer a host.
    rate_limit_s: float = 2.0
    daily_cap: int = 500

    enabled_by_default: bool = True
    warning: str = ""               # plain-language caution rendered on the UI card


PageOpener = Callable[[str], Awaitable[Any]]


@dataclass
class FetchContext:
    """Everything a source is handed. Sources never reach outside this."""

    profile: Profile
    queries: list[str]
    client: Any                             # httpx.AsyncClient, injected by the caller
    page_opener: PageOpener | None = None   # supplied by Track C's session vault
    limit: int = 100
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        """Record a non-fatal problem. Surfaces on the ScanRun, never raises."""
        self.warnings.append(message)

    async def open_page(self, portal: str) -> Any:
        """A Playwright page bound to `portal`'s persistent profile.

        Raises rather than returning None so a PORTAL source fails loudly and
        locally instead of producing a confusing empty result set.
        """
        if self.page_opener is None:
            raise SourceUnavailable(
                f"{portal}: no browser session provider is configured — "
                "the session vault is not running"
            )
        return await self.page_opener(portal)


@runtime_checkable
class Source(Protocol):
    meta: SourceMeta

    async def fetch(self, ctx: FetchContext) -> list[Job]: ...
