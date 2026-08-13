from app.models import Evaluation, Job
from app.sources.visa import needs_sponsorship_ok


def test_india_location_is_ok():
    j = Job(id="1", source="generic", company="c", title="SWE",
            location="Bengaluru, India", url="u1")
    assert needs_sponsorship_ok(j) is True


def test_no_sponsorship_flag_non_india_location_blocked():
    j = Job(id="2", source="generic", company="c", title="SWE",
            location="San Francisco, CA", url="u2")
    e = Evaluation(job_id="2", score=3.0, summary="s", cv_match="m", no_sponsorship=True)
    assert needs_sponsorship_ok(j, e) is False


def test_sponsor_friendly_source_overrides_no_sponsorship_flag():
    j = Job(id="3", source="h1bvisajobs", company="c", title="SWE",
            location="New York, NY", url="u3")
    e = Evaluation(job_id="3", score=3.0, summary="s", cv_match="m", no_sponsorship=True)
    assert needs_sponsorship_ok(j, e) is True


def test_remote_job_is_ok_even_with_no_sponsorship_flag():
    j = Job(id="4", source="remotive", company="c", title="SWE",
            location="Remote", url="u4")
    e = Evaluation(job_id="4", score=3.0, summary="s", cv_match="m", no_sponsorship=True)
    assert needs_sponsorship_ok(j, e) is True


def test_no_evaluation_defaults_to_ok():
    j = Job(id="5", source="generic", company="c", title="SWE",
            location="London, UK", url="u5")
    assert needs_sponsorship_ok(j) is True
