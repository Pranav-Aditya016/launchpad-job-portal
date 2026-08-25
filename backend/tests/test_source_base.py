import dataclasses

import pytest

from app.models import Job, Profile
from app.sources.base import (
    FetchContext, Source, SourceKind, SourceMeta, SourceUnavailable,
)


def test_source_meta_is_frozen():
    m = SourceMeta(key="k", label="K", kind=SourceKind.PUBLIC)
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.key = "other"


def test_source_meta_defaults_are_conservative():
    m = SourceMeta(key="k", label="K", kind=SourceKind.PUBLIC)
    assert m.regions == ("global",)
    assert m.requires_login is False
    assert m.rate_limit_s == 2.0
    assert m.daily_cap == 500
    assert m.enabled_by_default is True
    assert m.warning == ""


def test_portal_meta_carries_login_probe_fields():
    m = SourceMeta(
        key="naukri", label="Naukri", kind=SourceKind.PORTAL, regions=("in",),
        requires_login=True, login_url="https://www.naukri.com/nlogin/login",
        logged_in_probe="https://www.naukri.com/mnjuser/homepage",
        logged_in_selector="[data-test='profile-name']", rate_limit_s=4.0, daily_cap=200,
    )
    assert m.requires_login and m.logged_in_selector


def test_fetch_context_warn_accumulates():
    ctx = FetchContext(profile=Profile(), queries=["dev"], client=None)
    ctx.warn("naukri: timed out")
    ctx.warn("linkedin: blocked")
    assert ctx.warnings == ["naukri: timed out", "linkedin: blocked"]


async def test_open_page_without_a_browser_raises_clearly():
    ctx = FetchContext(profile=Profile(), queries=[], client=None)
    with pytest.raises(SourceUnavailable, match="no browser session provider"):
        await ctx.open_page("naukri")


def test_a_minimal_class_satisfies_the_source_protocol():
    class Dummy:
        meta = SourceMeta(key="dummy", label="Dummy", kind=SourceKind.PUBLIC)

        async def fetch(self, ctx: FetchContext) -> list[Job]:
            return []

    assert isinstance(Dummy(), Source)


def test_a_class_missing_fetch_does_not_satisfy_the_protocol():
    class Broken:
        meta = SourceMeta(key="broken", label="B", kind=SourceKind.PUBLIC)

    assert not isinstance(Broken(), Source)
