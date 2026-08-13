from app import llm
from app.models import Profile, Job, Evaluation, TailoredDoc

_SYS = (
  "You tailor a candidate's resume and write a cover letter for ONE job. "
  "Rewrite only from the candidate's real experience — never invent facts or "
  "employers. Return ONLY JSON with keys: cv_markdown (a full one-page CV in "
  "markdown, reordered/reworded to match the job) and cover_letter (150-200 words).")

def tailor(profile: Profile, job: Job, evaluation: Evaluation) -> TailoredDoc:
    user = (f"CANDIDATE:\n{profile.model_dump_json()}\n\nJOB: {job.title} @ {job.company}\n"
            f"{job.description[:5000]}\n\nEVAL STRENGTHS: {evaluation.strengths}\n"
            f"GAPS TO DOWNPLAY: {evaluation.gaps}")
    d = llm.complete_json(_SYS, user, max_tokens=2500)
    return TailoredDoc(job_id=job.id, cv_markdown=d.get("cv_markdown",""),
                       cover_letter=d.get("cover_letter",""))
