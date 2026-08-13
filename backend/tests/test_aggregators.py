import json
from pathlib import Path
from app.sources import aggregators as a

FX = Path(__file__).parent / "fixtures"

def _load(name): return json.loads((FX / name).read_text(encoding="utf-8"))

def test_parse_remotive():
    jobs = a.parse_remotive(_load("agg_remotive.json"))
    assert jobs and all(j.source == "remotive" and j.url and j.title for j in jobs)

def test_parse_arbeitnow():
    jobs = a.parse_arbeitnow(_load("agg_arbeitnow.json"))
    assert jobs and all(j.source == "arbeitnow" and j.url for j in jobs)

def test_parse_remoteok_skips_legal():
    jobs = a.parse_remoteok(_load("agg_remoteok.json"))
    assert jobs and all(j.source == "remoteok" and j.title for j in jobs)

def test_parse_jobicy():
    jobs = a.parse_jobicy(_load("agg_jobicy.json"))
    assert jobs and all(j.source == "jobicy" and j.url for j in jobs)

def test_parse_themuse():
    jobs = a.parse_themuse(_load("agg_themuse.json"))
    assert jobs and all(j.source == "themuse" and j.url for j in jobs)
