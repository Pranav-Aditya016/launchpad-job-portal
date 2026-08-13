import re
from app.models import Job

_ENTRY = ("intern", "internship", "junior", "jr ", "jr.", "entry level",
          "entry-level", "new grad", "new-grad", "graduate", "associate",
          "trainee", "apprentice", "0-2 year", "0 to 2 year", "early career",
          "fresher", "campus")
_SENIOR = ("senior", "sr ", "sr.", "staff", "principal", "lead ", "manager",
           "director", "head of", "architect", "vp ", "vice president",
           "executive", "expert", "10+ year", "distinguished")

def is_entry_level(title: str, description: str = "") -> bool:
    t = (title or "").lower()
    d = (description or "").lower()
    if any(s in t for s in _SENIOR):
        return False
    if any(e in t for e in _ENTRY):
        return True
    # title neutral: accept if the description signals early-career and doesn't shout senior
    if any(e in d for e in ("entry level", "entry-level", "new grad", "0-2 year",
                            "0 to 2 year", "recent graduate", "fresher")):
        return not any(s in d for s in ("senior", "principal", "staff", "5+ year", "7+ year"))
    return False

def experience_filter(jobs: list[Job]) -> list[Job]:
    return [j for j in jobs if is_entry_level(j.title, j.description)]
