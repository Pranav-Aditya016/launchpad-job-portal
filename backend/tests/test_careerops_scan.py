from pathlib import Path

import pytest

from app.sources import careerops_scan as s


def test_parse_scan_output_to_jobs():
    raw = (Path(__file__).parent / "fixtures" / "scan_sample.json").read_text()
    jobs = s.parse_scan_output(raw)
    assert len(jobs) >= 1
    j = jobs[0]
    assert j.url and j.company and j.title and j.id and j.source


def test_parse_scan_output_accepts_path():
    path = Path(__file__).parent / "fixtures" / "scan_sample.json"
    jobs = s.parse_scan_output(path)
    assert len(jobs) >= 1
    assert all(j.url and j.company and j.title and j.id and j.source for j in jobs)


def test_normalize_raw_offers_maps_fields_and_drops_extras():
    # Real RAW `--json` offer shape per task-4-report.md: company, title, url,
    # location, postedAt, dateStatus, blacklisted, note, source. Confirm the
    # normalized shape maps postedAt -> posted, keeps description empty, and
    # drops dateStatus/blacklisted/note.
    raw_offers = [
        {
            "company": "Acme",
            "title": "ML Engineer",
            "url": "https://job-boards.greenhouse.io/acme/jobs/1",
            "location": "Berlin, Germany",
            "postedAt": "2026-08-10",
            "dateStatus": "dated",
            "blacklisted": False,
            "note": None,
            "source": "greenhouse-full",
        },
        {
            "company": "Beta",
            "title": "Data Scientist",
            "url": "https://job-boards.greenhouse.io/beta/jobs/2",
            "location": "Remote",
            "postedAt": None,
            "dateStatus": "unknown",
            "blacklisted": False,
            "note": "reposted",
            "source": "greenhouse-full",
        },
    ]

    normalized = s._normalize_raw_offers(raw_offers)

    assert normalized == [
        {
            "company": "Acme",
            "title": "ML Engineer",
            "location": "Berlin, Germany",
            "url": "https://job-boards.greenhouse.io/acme/jobs/1",
            "posted": "2026-08-10",
            "source": "greenhouse-full",
            "description": "",
        },
        {
            "company": "Beta",
            "title": "Data Scientist",
            "location": "Remote",
            "url": "https://job-boards.greenhouse.io/beta/jobs/2",
            "posted": None,
            "source": "greenhouse-full",
            "description": "",
        },
    ]


def test_normalize_raw_offers_defaults_missing_keys():
    normalized = s._normalize_raw_offers([{}])
    assert normalized == [
        {
            "company": "",
            "title": "",
            "location": "",
            "url": "",
            "posted": None,
            "source": "careerops",
            "description": "",
        }
    ]


def test_extract_json_payload_parses_clean_stdout():
    stdout = '{"date": "2026-08-14", "offers": [{"company": "Acme", "title": "SWE"}]}'
    payload = s._extract_json_payload(stdout)
    assert payload["offers"][0]["company"] == "Acme"
    assert payload["offers"][0]["title"] == "SWE"


def test_extract_json_payload_skips_leading_non_json_noise():
    # Defensive case: something prints ahead of the JSON object on stdout
    # (e.g. a misbehaving dependency). Parsing should start at the first `{`.
    stdout = 'warning: some noise\n{"offers": [{"company": "Beta"}]}'
    payload = s._extract_json_payload(stdout)
    assert payload["offers"] == [{"company": "Beta"}]


def test_extract_json_payload_raises_when_no_json_object_found():
    with pytest.raises(ValueError):
        s._extract_json_payload("no json here at all")
