from pathlib import Path
from markitdown import MarkItDown
from app import llm
from app.models import Profile

_EXTRACT_SYS = (
  "You extract a job candidate's structured profile from resume text. "
  "Return ONLY JSON with keys: name, email, location, work_auth "
  "(their stated work authorization / visa status, empty string if unknown), "
  "target_roles (list), skills (list), proof_points (list of concrete achievements). "
  "Do not invent facts.")

def extract_text(path: Path) -> str:
    return MarkItDown().convert(str(path)).text_content

def build_profile(resume_text: str) -> Profile:
    data = llm.complete_json(_EXTRACT_SYS, f"RESUME:\n{resume_text[:8000]}")
    return Profile(resume_text=resume_text, **{k: data.get(k) or ([] if k in
        ("target_roles","skills","proof_points") else "") for k in
        ("name","email","location","work_auth","target_roles","skills","proof_points")})

def ingest(path: Path) -> Profile:
    return build_profile(extract_text(path))
