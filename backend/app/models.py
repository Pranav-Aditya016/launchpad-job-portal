"""Core data models.

The text/list fields are coercing rather than strict. Every one of these is
populated from LLM output, and smaller local models (qwen3:8b via Ollama) are
noticeably looser about types than the hosted ones — returning `cv_match: 2.5`
where a string was asked for, or a bare string where a list was. Rejecting the
whole evaluation over that throws away an otherwise-good result, so we normalize
instead. Real type errors in our own code still surface, because these only
widen JSON scalars into the declared shape.
"""

import hashlib

from pydantic import BaseModel, Field, field_validator


def job_id(source: str, company: str, url: str) -> str:
    return hashlib.sha256(f"{source}:{company}:{url}".encode()).hexdigest()[:16]


def _to_str(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v)
    if isinstance(v, dict):
        return " ".join(f"{k}: {val}" for k, val in v.items())
    return str(v)


def _to_str_list(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    if isinstance(v, (list, tuple)):
        return [_to_str(x) for x in v if x is not None and _to_str(x).strip()]
    if isinstance(v, dict):
        return [f"{k}: {_to_str(val)}" for k, val in v.items()]
    return [_to_str(v)]


class Profile(BaseModel):
    name: str = ""
    email: str = ""
    location: str = ""
    work_auth: str = ""
    target_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    resume_text: str = ""

    @field_validator("name", "email", "location", "work_auth", "resume_text", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return _to_str(v)

    @field_validator("target_roles", "skills", "proof_points", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        return _to_str_list(v)


class Job(BaseModel):
    id: str
    source: str
    company: str
    title: str
    location: str = ""
    url: str
    description: str = ""
    posted: str | None = None

    @field_validator("company", "title", "location", "description", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return _to_str(v)


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

    @field_validator("summary", "cv_match", "scam_reason", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return _to_str(v)

    @field_validator("strengths", "gaps", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        return _to_str_list(v)

    @field_validator("score", mode="before")
    @classmethod
    def _coerce_score(cls, v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0


class TailoredDoc(BaseModel):
    job_id: str
    cv_markdown: str
    cover_letter: str

    @field_validator("cv_markdown", "cover_letter", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return _to_str(v)
