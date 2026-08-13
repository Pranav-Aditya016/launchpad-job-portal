from pathlib import Path

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
