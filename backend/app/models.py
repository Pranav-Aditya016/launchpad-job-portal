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
from typing import Literal

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
    region: str = ""              # "in" | "de" | "global" — from the source's meta
    first_seen: str | None = None # ISO-8601, set on first upsert

    @field_validator("company", "title", "location", "description", "region", mode="before")
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


ConnectionStatus = Literal["disconnected", "connected", "expired", "checking", "blocked"]
QueueState = Literal["ready", "prepared", "submitted", "skipped"]


class Connection(BaseModel):
    """Status of ONE login-gated portal.

    Deliberately holds no credential of any kind. LaunchPad never sees the user's
    password: they log in themselves in a real browser window and we persist only
    the resulting browser profile on local disk (spec §6.3). If you are ever
    tempted to add a `password` field here, re-read spec §2.
    """

    portal: str
    status: ConnectionStatus = "disconnected"
    last_verified: str | None = None   # ISO-8601
    note: str = ""                     # human-readable last error, shown in the UI

    @field_validator("note", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return _to_str(v)


class ScanRun(BaseModel):
    """One scan cycle, manual or scheduled."""

    id: str
    started: str
    finished: str | None = None
    trigger: Literal["manual", "scheduled"] = "manual"
    per_source: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    evaluated: int = 0
    tailored: int = 0
    partial: bool = False   # True when the 20-minute cycle cap cut the run short

    @field_validator("warnings", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        return _to_str_list(v)


class QueueItem(BaseModel):
    """A prepared application awaiting the user's own submit click.

    `submitted` means the USER told us they submitted it. Nothing in this system
    presses a submit button (spec §2, §6.5).
    """

    job_id: str
    state: QueueState = "ready"
    score: float = 0.0
    prepared_at: str | None = None
    submitted_at: str | None = None
    cv_pdf: str | None = None   # path relative to launchpad_data/output
    notes: str = ""

    @field_validator("notes", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return _to_str(v)

    @field_validator("score", mode="before")
    @classmethod
    def _coerce_score(cls, v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
