"""GET /config — what the backend can actually do right now.

Moved out of api.py so Track A can extend the offline-readiness report without
touching a file any other track needs.
"""

import os

from fastapi import APIRouter

from app import config, llm
# `pdf` is either the weasyprint-backed module or None, guarded once in
# app/tailor/__init__.py (a failed submodule import isn't cached in
# sys.modules, so re-guarding it here would re-run WeasyPrint's failing
# import and print its stderr banner a second time).
from app.tailor import pdf

router = APIRouter()


@router.get("/config")
def get_config():
    provider = llm.provider()
    if provider == "api":
        llm_available = bool(os.environ.get("ANTHROPIC_API_KEY"))
    elif provider == "cli":
        llm_available = llm.claude_cli_path() is not None
    else:
        llm_available = llm.ollama_available()
    return {
        "llm_available": llm_available,
        "llm_provider": provider,
        "llm_model": llm.OLLAMA_MODEL if provider == "ollama" else config.LLM_MODEL,
        "pdf_available": pdf is not None,
        "adzuna_available": bool(
            os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY")
        ),
    }
