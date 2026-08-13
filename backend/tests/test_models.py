from app.models import Job, job_id, Evaluation

def test_job_id_stable():
    a = job_id("greenhouse", "stripe", "https://x/y")
    b = job_id("greenhouse", "stripe", "https://x/y")
    assert a == b and len(a) == 16

def test_evaluation_defaults():
    e = Evaluation(job_id="j1", score=4.2, summary="s", cv_match="m")
    assert e.scam_flag is False and e.no_sponsorship is False
