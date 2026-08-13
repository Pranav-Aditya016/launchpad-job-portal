import json
from pathlib import Path
from app.sources import aggregators as a

FX = Path(__file__).parent / "fixtures"

def _load(name): return json.loads((FX / name).read_text(encoding="utf-8"))

def test_parse_remotive():
    jobs = a.parse_remotive(_load("agg_remotive.json"))
    assert jobs and all(j.source == "remotive" and j.url and j.title for j in jobs)
    # Shape-only assertions (source/url/title truthiness) would still pass if
    # title and company were swapped. Pin an actual value from the fixture.
    assert jobs[0].title == "Assistant Account Payable"
    assert jobs[0].company == "The Obesity Society"

def test_parse_arbeitnow():
    jobs = a.parse_arbeitnow(_load("agg_arbeitnow.json"))
    assert jobs and all(j.source == "arbeitnow" and j.url for j in jobs)
    assert jobs[0].title == "Software Engineer"
    assert jobs[0].company == "Preiswecker"

def test_parse_remoteok_skips_legal():
    jobs = a.parse_remoteok(_load("agg_remoteok.json"))
    assert jobs and all(j.source == "remoteok" and j.title for j in jobs)
    assert jobs[0].title == "Software Engineer III Mobile"
    assert jobs[0].company == "Stone"

def test_parse_jobicy():
    jobs = a.parse_jobicy(_load("agg_jobicy.json"))
    assert jobs and all(j.source == "jobicy" and j.url for j in jobs)
    assert jobs[0].title == "Customer Success Engineer, UK"
    assert jobs[0].company == "Nash"

def test_parse_themuse():
    jobs = a.parse_themuse(_load("agg_themuse.json"))
    assert jobs and all(j.source == "themuse" and j.url for j in jobs)
    assert jobs[0].title == "Pediatric Private Duty RN LVN"
    assert jobs[0].company == "Thrive Skilled Pediatric Care LLC"

def test_clean_decodes_html_entities():
    # Real providers (e.g. Arbeitnow) return entity-encoded descriptions like
    # "&lt;p&gt;...&lt;/p&gt;" — _clean must unescape THEN strip tags, not
    # leave the entity soup untouched (Task 14 quality fix).
    assert a._clean("&lt;p&gt;Hello&lt;/p&gt; &amp; more") == "Hello & more"

def test_parse_adzuna():
    jobs = a.parse_adzuna(_load("agg_adzuna.json"), "in")
    assert jobs and all(j.source.startswith("adzuna-") and j.url and j.company for j in jobs)
    assert jobs[0].url.startswith("http")
    assert jobs[0].company == "Infosys Limited"


async def test_fetch_all_respects_providers_filter_for_adzuna(monkeypatch):
    # Regression test: fetch_adzuna used to be appended to the task list
    # unconditionally, outside the `providers` filter — so `providers=["remotive"]`
    # (intended to mean "only remotive") silently still hit Adzuna too.
    calls: list[str] = []

    async def _fake_fetch_one(client, name, query):
        calls.append(name)
        return []

    async def _fake_fetch_adzuna(client, query, countries=None):
        calls.append("adzuna")
        return []

    monkeypatch.setattr(a, "_fetch_one", _fake_fetch_one)
    monkeypatch.setattr(a, "fetch_adzuna", _fake_fetch_adzuna)

    await a.fetch_all(providers=["remotive"], fresher_only=False)
    assert calls == ["remotive"]

    calls.clear()
    await a.fetch_all(providers=["remotive", "adzuna"], fresher_only=False)
    assert set(calls) == {"remotive", "adzuna"}

    calls.clear()
    await a.fetch_all(providers=None, fresher_only=False)
    assert "adzuna" in calls
