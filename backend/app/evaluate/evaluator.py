from app import llm
from app.evaluate.rubric import load_rubric
from app.models import Profile, Job, Evaluation

_SYS = (
    "You are a rigorous job-fit evaluator. Apply the rubric below. "
    "Return ONLY JSON with keys: score (1-5 float), summary, cv_match, "
    "scam_flag (bool), scam_reason, no_sponsorship (bool: true if the posting "
    "explicitly refuses visa sponsorship), strengths (list), gaps (list).\n\nRUBRIC:\n")


def evaluate(profile: Profile, job: Job) -> Evaluation:
    sys = _SYS + load_rubric()[:12000]
    user = (f"CANDIDATE:\n{profile.model_dump_json()}\n\n"
            f"JOB: {job.title} @ {job.company}\n{job.description[:6000]}")
    d = llm.complete_json(sys, user)
    return Evaluation(job_id=job.id, score=float(d.get("score", 0)),
        summary=d.get("summary", ""), cv_match=d.get("cv_match", ""),
        scam_flag=bool(d.get("scam_flag")), scam_reason=d.get("scam_reason", ""),
        no_sponsorship=bool(d.get("no_sponsorship")),
        strengths=d.get("strengths", []), gaps=d.get("gaps", []))
