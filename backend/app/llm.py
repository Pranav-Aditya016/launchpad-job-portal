import json, re, os
from anthropic import Anthropic
from app import config as cfg

_client = None
def _c():
    global _client
    if _client is None: _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client

def complete_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    resp = _c().messages.create(model=cfg.LLM_MODEL, max_tokens=max_tokens,
        system=system, messages=[{"role": "user", "content": user}])
    text = resp.content[0].text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)
