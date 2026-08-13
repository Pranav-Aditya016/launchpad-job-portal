import hashlib
from pydantic import BaseModel, Field

def job_id(source: str, company: str, url: str) -> str:
    return hashlib.sha256(f"{source}:{company}:{url}".encode()).hexdigest()[:16]

class Profile(BaseModel):
    name: str = ""
    email: str = ""
    location: str = ""
    work_auth: str = ""
    target_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    resume_text: str = ""

class Job(BaseModel):
    id: str
    source: str
    company: str
    title: str
    location: str = ""
    url: str
    description: str = ""
    posted: str | None = None

class Evaluation(BaseModel):
    job_id: str
    score: float
    summary: str
    cv_match: str
    scam_flag: bool = False
    scam_reason: str = ""
    no_sponsorship: bool = False
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

class TailoredDoc(BaseModel):
    job_id: str
    cv_markdown: str
    cover_letter: str
