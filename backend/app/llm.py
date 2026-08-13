import json, re, os
from anthropic import Anthropic
from app import config as cfg

_client = None
def _c():
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            # A bare os.environ[...] KeyError here used to surface as an opaque
            # 500 on the very first /evaluate or /tailor call (the most likely
            # first-run failure). Raise something callers can recognize and
            # map to a clean 400 instead (see app/api.py).
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set — required for evaluation and tailoring"
            )
        _client = Anthropic(api_key=api_key)
    return _client

_FENCE = re.compile(r"^```[a-zA-Z0-9]*\s*\n?(.*?)\n?```$", re.DOTALL)

def _strip_fence(text: str) -> str:
    text = text.strip()
    m = _FENCE.match(text)
    return m.group(1).strip() if m else text

def complete_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    resp = _c().messages.create(model=cfg.LLM_MODEL, max_tokens=max_tokens,
        system=system, messages=[{"role": "user", "content": user}])
    return json.loads(_strip_fence(resp.content[0].text))
