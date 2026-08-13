from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "launchpad_data"
ENGINE_DIR = REPO_ROOT / "engine" / "career-ops"
OUTPUT_DIR = DATA_DIR / "output"
EVAL_DIR = DATA_DIR / "evaluations"
LLM_MODEL = "claude-opus-4-6"

for d in (DATA_DIR, OUTPUT_DIR, EVAL_DIR):
    d.mkdir(parents=True, exist_ok=True)
