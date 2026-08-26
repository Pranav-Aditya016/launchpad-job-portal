"""Turn an uploaded resume file into a structured Profile.

Budgeted and validated like the other call sites: an over-long prompt costs the
system message on the local provider, and reading the reply with `.get(key)`
alone would turn that into a blank profile saved as a success.
"""

from pathlib import Path

from markitdown import MarkItDown

from app import llm
from app.models import Profile

_LIST_FIELDS = ("target_roles", "skills", "proof_points")
_STR_FIELDS = ("name", "email", "location", "work_auth")

_EXTRACT_SYS = (
    "You extract a job candidate's structured profile from resume text. "
    "Return ONLY JSON with keys: name, email, location, work_auth "
    "(their stated work authorization / visa status, empty string if unknown), "
    "target_roles (list), skills (list), proof_points (list of concrete achievements). "
    "Do not invent facts.")


def extract_text(path: Path) -> str:
    return MarkItDown().convert(str(path)).text_content


def build_prompts(resume_text: str) -> tuple[str, str]:
    """(system, user) sized to fit the active provider's context window.

    Only the PROMPT is trimmed — `build_profile` stores the full resume text on
    the Profile, because tailoring and any future re-parse need all of it.
    """
    budget = llm.prompt_budget_chars()
    room = max(0, budget - len(_EXTRACT_SYS) - len("RESUME:\n"))
    return _EXTRACT_SYS, f"RESUME:\n{resume_text[:room]}"


def build_profile(resume_text: str) -> Profile:
    system, user = build_prompts(resume_text)
    data = llm.require_json_keys(
        llm.complete_json(system, user), ("name", "skills"), "resume ingest",
    )
    fields = {k: (data.get(k) or "") for k in _STR_FIELDS}
    fields.update({k: (data.get(k) or []) for k in _LIST_FIELDS})
    return Profile(resume_text=resume_text, **fields)


def ingest(path: Path) -> Profile:
    return build_profile(extract_text(path))
