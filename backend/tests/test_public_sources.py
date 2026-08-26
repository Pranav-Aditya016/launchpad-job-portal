"""Fixture-based tests for the seven public_*.py adapters (Track B).

No network. Six of these wrap `aggregators.py`'s existing, already-tested
parsers unchanged (see `test_aggregators.py` for the parser-level fixtures
that cover Remotive/Arbeitnow/RemoteOK/Jobicy/The Muse/Adzuna in depth — this
file re-uses the SAME fixture files rather than duplicating them, and focuses
on what's new here: the `Source.fetch()` wiring, `ctx.limit`, non-fatal
failure, and the query-string passthrough). The seventh, arbeitsagentur, is
new and documented as unverified live (see its module docstring) — its
fixture is schema-derived, not a live capture, and that's asserted here too.
"""

import json
import os
from pathlib import Path

import pytest

from app.models import Profile
from app.sources import aggregators
from app.sources.base import FetchContext, SourceKind
from app.sources.providers import (
    public_adzuna, public_arbeitnow, public_arbeitsagentur, public_jobicy,
    public_remoteok, public_remotive, public_themuse,
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
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def get(self, url, params=None, headers=None):
        self.calls.append(url)
        return _Resp(self._payload)


class _BrokenClient:
    async def get(self, url, params=None, headers=None):
        raise ConnectionError("simulated network failure")


def _ctx(client, limit=100, queries=None):
    return FetchContext(profile=Profile(), queries=queries or [], client=client, limit=limit)


_SIMPLE_ADAPTERS = [
    (public_remotive, "RemotiveSource", "agg_remotive.json"),
    (public_arbeitnow, "ArbeitnowSource", "agg_arbeitnow.json"),
    (public_remoteok, "RemoteOKSource", "agg_remoteok.json"),
    (public_jobicy, "JobicySource", "agg_jobicy.json"),
    (public_themuse, "TheMuseSource", "agg_themuse.json"),
]


@pytest.mark.parametrize("module,cls_name,fixture", _SIMPLE_ADAPTERS)
async def test_fetch_wraps_the_existing_aggregator_parser(module, cls_name, fixture):
    source = getattr(module, cls_name)()
    ctx = _ctx(_FakeClient(_load(fixture)))
    jobs = await source.fetch(ctx)
    assert jobs, f"{cls_name} produced no jobs from a fixture with real ones"
    # Job.source must stay the UNPREFIXED v1 name (e.g. "remotive") so job_id()
    # keeps producing the same id for the same real posting as v1 always did —
    # only the registry key (meta.key) gets the "public:" namespace.
    assert jobs[0].source == source.meta.key.split(":", 1)[1]


@pytest.mark.parametrize("module,cls_name,fixture", _SIMPLE_ADAPTERS)
async def test_fetch_is_non_fatal_on_network_failure(module, cls_name, fixture):
    source = getattr(module, cls_name)()
    ctx = _ctx(_BrokenClient())
    jobs = await source.fetch(ctx)
    assert jobs == []
    assert len(ctx.warnings) == 1
    assert source.meta.key in ctx.warnings[0]


@pytest.mark.parametrize("module,cls_name,fixture", _SIMPLE_ADAPTERS)
async def test_fetch_honours_ctx_limit(module, cls_name, fixture):
    source = getattr(module, cls_name)()
    data = _load(fixture)
    ctx = _ctx(_FakeClient(data), limit=1)
    jobs = await source.fetch(ctx)
    assert len(jobs) <= 1


async def test_remotive_appends_search_query_to_the_url():
    source = public_remotive.RemotiveSource()
    client = _FakeClient(_load("agg_remotive.json"))
    ctx = _ctx(client, queries=["backend engineer"])
    await source.fetch(ctx)
    assert any("search=backend engineer" in url for url in client.calls)


# --- Adzuna: opt-in via env vars, multi-country, per-country non-fatal ----

async def test_adzuna_is_a_harmless_noop_without_env_vars(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    source = public_adzuna.AdzunaSource()
    client = _FakeClient(_load("agg_adzuna.json"))
    ctx = _ctx(client)
    jobs = await source.fetch(ctx)
    assert jobs == []
    assert client.calls == []  # never even tried to call out


async def test_adzuna_fetches_when_env_vars_are_set(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "test-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test-key")
    source = public_adzuna.AdzunaSource()
    client = _FakeClient(_load("agg_adzuna.json"))
    ctx = _ctx(client, limit=3)
    jobs = await source.fetch(ctx)
    assert jobs
    assert len(jobs) <= 3
    assert len(client.calls) == len(aggregators.ADZUNA_COUNTRIES)  # one call per country


async def test_adzuna_meta_warns_about_the_credential_requirement():
    assert "ADZUNA_APP_ID" in public_adzuna.AdzunaSource.meta.warning


# --- arbeitsagentur: disabled by default, schema-derived fixture ----------

def test_parse_arbeitsagentur_against_schema_derived_fixture():
    data = _load("public_arbeitsagentur.json")
    assert data.get("_note", "").startswith("SCHEMA-DERIVED")  # honesty check on the fixture itself
    jobs = public_arbeitsagentur.parse_arbeitsagentur(data)
    assert len(jobs) == 2
    assert all(j.source == "public:arbeitsagentur" and j.region == "de" for j in jobs)
    assert jobs[0].company == "Muster GmbH"
    assert jobs[0].title == "Softwareentwickler (m/w/d)"


async def test_arbeitsagentur_fetch_against_fake_client():
    source = public_arbeitsagentur.ArbeitsagenturSource()
    ctx = _ctx(_FakeClient(_load("public_arbeitsagentur.json")))
    jobs = await source.fetch(ctx)
    assert len(jobs) == 2


def test_arbeitsagentur_is_disabled_by_default_and_explains_why():
    meta = public_arbeitsagentur.ArbeitsagenturSource.meta
    assert meta.enabled_by_default is False
    assert "403" in meta.warning or "401" in meta.warning


async def test_arbeitsagentur_fetch_is_non_fatal_on_failure():
    source = public_arbeitsagentur.ArbeitsagenturSource()
    ctx = _ctx(_BrokenClient())
    jobs = await source.fetch(ctx)
    assert jobs == []
    assert len(ctx.warnings) == 1


# --- meta sanity across every public_* source registered ------------------

_ALL_PUBLIC_SOURCES = [
    public_remotive.RemotiveSource,
    public_arbeitnow.ArbeitnowSource,
    public_remoteok.RemoteOKSource,
    public_jobicy.JobicySource,
    public_themuse.TheMuseSource,
    public_adzuna.AdzunaSource,
    public_arbeitsagentur.ArbeitsagenturSource,
]


def test_every_public_source_has_a_unique_prefixed_key_and_valid_meta():
    keys = [cls.meta.key for cls in _ALL_PUBLIC_SOURCES]
    assert len(keys) == len(set(keys)), "duplicate public: source keys"
    for cls in _ALL_PUBLIC_SOURCES:
        m = cls.meta
        assert m.key.startswith("public:")
        assert m.label
        assert m.kind == SourceKind.PUBLIC
        assert isinstance(m.regions, tuple) and m.regions
        assert m.rate_limit_s > 0
        assert m.daily_cap > 0
