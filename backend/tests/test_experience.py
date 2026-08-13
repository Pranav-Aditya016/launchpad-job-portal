from app.sources.experience import is_entry_level, experience_filter
from app.models import Job

def test_entry_level_positive():
    assert is_entry_level("Junior Software Engineer")
    assert is_entry_level("New Grad Data Analyst")
    assert is_entry_level("Software Engineer Intern")
    assert is_entry_level("Associate Developer", "0-2 years experience")

def test_entry_level_negative():
    assert not is_entry_level("Senior Software Engineer")
    assert not is_entry_level("Staff Engineer")
    assert not is_entry_level("Engineering Manager")
    assert not is_entry_level("Principal Architect")

def test_experience_filter_keeps_only_entry():
    jobs = [Job(id="1", source="s", company="c", title="Senior Engineer", url="u1"),
            Job(id="2", source="s", company="c", title="Junior Engineer", url="u2")]
    kept = experience_filter(jobs)
    assert [j.id for j in kept] == ["2"]
