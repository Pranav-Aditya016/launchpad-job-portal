import json, re, os
from anthropic import Anthropic
from app import config as cfg

_client = None
def _c():
    global _client
    if _client is None: _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
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
