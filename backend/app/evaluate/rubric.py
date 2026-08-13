from functools import lru_cache
from app import config as cfg


@lru_cache
def load_rubric() -> str:
    modes = cfg.ENGINE_DIR / "modes"
    parts = []
    for name in ("_shared.md", "oferta.md"):
        f = modes / name
        if f.exists():
            parts.append(f.read_text(encoding="utf-8"))
    return "\n\n".join(parts)
