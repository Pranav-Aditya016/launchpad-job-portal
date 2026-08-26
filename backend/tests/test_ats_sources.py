"""Fixture-based tests for the eight ats_*.py adapters (Track B).

No network. Every parser is exercised against a real trimmed API response
captured in `tests/fixtures/ats_*.json` (see the adapter module docstrings
for the exact live call each one was captured from). Every `Source.fetch()`
is exercised against a fake httpx-shaped client so the full request -> parse
-> Job path runs without touching the network, including the non-fatal
per-company failure path the handoff requires.
"""

import json
from pathlib import Path

import pytest

from app.models import Job, Profile
from app.sources.base import FetchContext
from app.sources.providers import (
    ats_ashby, ats_common, ats_greenhouse, ats_lever, ats_personio,
    ats_recruitee, ats_smartrecruiters, ats_workable, ats_workday,
)

FX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient: always answers with the same payload."""

    def __init__(self, payload):
        self._payload = payload

    async def get(self, url, params=None, headers=None):
        return _Resp(self._payload)

    async def post(self, url, json=None):
        return _Resp(self._payload)


class _BrokenClient:
    """Every call raises — proves per-company failures are non-fatal."""

    async def get(self, url, params=None, headers=None):
        raise ConnectionError("simulated network failure")

    async def post(self, url, json=None):
        raise ConnectionError("simulated network failure")


def _ctx(client, limit=100):
    return FetchContext(profile=Profile(), queries=[], client=client, limit=limit)


# --- parser-level tests, one per adapter, against a real captured fixture --

def test_parse_greenhouse():
    jobs = ats_greenhouse.parse_greenhouse(_load("ats_greenhouse.json"), "Databricks", "global")
    assert jobs and all(isinstance(j, Job) and j.source == "ats:greenhouse" for j in jobs)
    assert jobs[0].url.startswith("http")
    assert jobs[0].company == "Databricks"
    assert jobs[0].region == "global"


def test_parse_lever():
    jobs = ats_lever.parse_lever(_load("ats_lever.json"), "Spotify", "global")
    assert jobs and all(j.source == "ats:lever" for j in jobs)
    assert jobs[0].title
    assert jobs[0].url.startswith("http")


def test_parse_ashby():
    jobs = ats_ashby.parse_ashby(_load("ats_ashby.json"), "Ramp", "global")
    assert jobs and all(j.source == "ats:ashby" for j in jobs)
    assert jobs[0].title.strip() == "Security Engineer, Cloud"
    assert jobs[0].url.startswith("http")


def test_parse_smartrecruiters():
    jobs = ats_smartrecruiters.parse_smartrecruiters(_load("ats_smartrecruiters.json"), "Sixt", "de")
    assert jobs and all(j.source == "ats:smartrecruiters" for j in jobs)
    assert jobs[0].url.startswith("https://jobs.smartrecruiters.com/")
    assert jobs[0].region == "de"


def test_parse_workable():
    jobs = ats_workable.parse_workable(_load("ats_workable.json"), "Hugging Face", "global")
    assert jobs and all(j.source == "ats:workable" for j in jobs)
    assert jobs[0].url.startswith("http")
    assert jobs[0].company == "Hugging Face"


def test_parse_recruitee():
    jobs = ats_recruitee.parse_recruitee(_load("ats_recruitee.json"), "Helloprint", "global")
    assert jobs and all(j.source == "ats:recruitee" for j in jobs)
    assert jobs[0].title == "Senior Test Automation Engineer"
    assert jobs[0].url.startswith("http")


def test_parse_personio():
    raw = _load("ats_personio.json")
    jobs = ats_personio.parse_personio(raw, "Medwing", "de", "medwing")
    assert jobs and all(j.source == "ats:personio" for j in jobs)
    assert jobs[0].url == f"https://medwing.jobs.personio.de/job/{raw[0]['id']}"
    assert jobs[0].region == "de"


def test_parse_workday():
    jobs = ats_workday.parse_workday(
        _load("ats_workday.json"), "Accenture", "global", "accenture", "wd103", "AccentureCareers"
    )
    assert jobs and all(j.source == "ats:workday" for j in jobs)
    assert jobs[0].url.startswith("https://accenture.wd103.myworkdayjobs.com/AccentureCareers")
    assert jobs[0].title


# --- fetch()-level tests: fake client + monkeypatched companies.yml lookup --

_ADAPTERS = [
    (ats_greenhouse, "GreenhouseSource", "greenhouse", "ats_greenhouse.json", {}),
    (ats_lever, "LeverSource", "lever", "ats_lever.json", {}),
    (ats_ashby, "AshbySource", "ashby", "ats_ashby.json", {}),
    (ats_smartrecruiters, "SmartRecruitersSource", "smartrecruiters", "ats_smartrecruiters.json", {}),
    (ats_workable, "WorkableSource", "workable", "ats_workable.json", {}),
    (ats_recruitee, "RecruiteeSource", "recruitee", "ats_recruitee.json", {}),
    (ats_personio, "PersonioSource", "personio", "ats_personio.json", {}),
    (ats_workday, "WorkdaySource", "workday", "ats_workday.json", {"wd_host": "wd103", "site": "AccentureCareers"}),
]


@pytest.mark.parametrize("module,cls_name,ats_key,fixture,extra", _ADAPTERS)
@pytest.mark.asyncio
async def test_fetch_succeeds_with_fake_client(monkeypatch, module, cls_name, ats_key, fixture, extra):
    company = {"name": "TestCo", "slug": "testco", "regions": ["global"], **extra}
    monkeypatch.setattr(ats_common, "companies_for", lambda ats: [company] if ats == ats_key else [])

    source = getattr(module, cls_name)()
    ctx = _ctx(_FakeClient(_load(fixture)))
    jobs = await source.fetch(ctx)

    assert jobs, f"{cls_name} returned no jobs from a fixture known to have some"
    assert all(j.company == "TestCo" for j in jobs)
    assert ctx.warnings == []


@pytest.mark.parametrize("module,cls_name,ats_key,fixture,extra", _ADAPTERS)
@pytest.mark.asyncio
async def test_fetch_is_non_fatal_when_a_company_fails(monkeypatch, module, cls_name, ats_key, fixture, extra):
    """One dead company must not crash the whole fetch — it warns and moves on."""
    company = {"name": "DeadCo", "slug": "deadco", "regions": ["global"], **extra}
    monkeypatch.setattr(ats_common, "companies_for", lambda ats: [company] if ats == ats_key else [])

    source = getattr(module, cls_name)()
    ctx = _ctx(_BrokenClient())
    jobs = await source.fetch(ctx)

    assert jobs == []
    assert len(ctx.warnings) == 1
    assert "DeadCo" in ctx.warnings[0] or "deadco" in ctx.warnings[0]


async def test_fetch_honours_ctx_limit(monkeypatch):
    company = {"name": "Databricks", "slug": "databricks", "regions": ["global"]}
    monkeypatch.setattr(ats_common, "companies_for", lambda ats: [company] if ats == "greenhouse" else [])

    source = ats_greenhouse.GreenhouseSource()
    with_two_jobs = _load("ats_greenhouse.json")
    assert len(with_two_jobs["jobs"]) == 2

    ctx = _ctx(_FakeClient(with_two_jobs), limit=1)
    jobs = await source.fetch(ctx)
    assert len(jobs) == 1


async def test_workday_source_warns_when_yaml_entry_is_missing_wd_fields():
    company = {"name": "Broken Co", "slug": "brokenco", "regions": ["global"]}  # no wd_host/site
    import app.sources.providers.ats_common as common_mod
    orig = common_mod.companies_for
    common_mod.companies_for = lambda ats: [company] if ats == "workday" else []
    try:
        source = ats_workday.WorkdaySource()
        ctx = _ctx(_FakeClient({}))
        jobs = await source.fetch(ctx)
        assert jobs == []
        assert len(ctx.warnings) == 1
        assert "wd_host" in ctx.warnings[0]
    finally:
        common_mod.companies_for = orig


# --- companies.yml sanity ---------------------------------------------

def test_companies_yaml_loads_and_has_60_plus_entries():
    ats_common._companies_cache = None  # force a fresh read of the real file
    all_companies = ats_common._load_all_companies()
    assert len(all_companies) >= 60
    for c in all_companies:
        assert c.get("name")
        assert c.get("ats")
        assert c.get("slug")
        assert isinstance(c.get("regions"), list) and c["regions"]


def test_every_company_ats_value_has_a_matching_adapter():
    ats_common._companies_cache = None
    known = {"greenhouse", "lever", "ashby", "smartrecruiters", "workable", "recruitee", "personio", "workday"}
    all_companies = ats_common._load_all_companies()
    assert {c["ats"] for c in all_companies} <= known
