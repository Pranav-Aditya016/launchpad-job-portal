"""Single LLM call site, with two interchangeable providers.

- **cli** (default when no API key): shells out to the Claude Code CLI in headless
  print mode (`claude -p`). This authenticates with the user's Claude Pro/Max
  subscription, so it needs no API key and consumes no API credits. It is the
  pattern career-ops documents for its own batch workers ("headless CLI workers:
  `claude -p` / `opencode run`"), and it is subject to the subscription's own
  rate limits rather than API billing.
- **api**: the Anthropic SDK with `ANTHROPIC_API_KEY`. Faster and parallel-friendly,
  but requires credit on the API account (a Pro subscription does NOT fund it).

Select explicitly with `LAUNCHPAD_LLM=cli|api`; the default (`auto`) prefers the
API when a key is present and otherwise falls back to the CLI.
"""

import json
import os
import re
import shutil
import subprocess

from app import config as cfg

_client = None


def _api_client():
    global _client
    if _client is None:
        from anthropic import Anthropic

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


def claude_cli_path() -> str | None:
    """Path to the Claude Code CLI, or None if it isn't installed."""
    return shutil.which("claude")


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
# qwen3:8b at Q4_K_M is ~5.2GB — fits an 8GB card with room for context, and
# follows JSON instructions well. Override for a different local model.
OLLAMA_MODEL = os.environ.get("LAUNCHPAD_OLLAMA_MODEL", "qwen3:8b")


def ollama_available() -> bool:
    try:
        import httpx

        return httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


def provider() -> str:
    """Which backend a call will use right now: 'api', 'cli' or 'ollama'."""
    choice = (os.environ.get("LAUNCHPAD_LLM") or "auto").lower()
    if choice in ("api", "cli", "ollama"):
        return choice
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api"
    if claude_cli_path():
        return "cli"
    return "ollama"


_FENCE = re.compile(r"^```[a-zA-Z0-9]*\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_fence(text: str) -> str:
    text = text.strip()
    m = _FENCE.match(text)
    return m.group(1).strip() if m else text


def _complete_json_cli(system: str, user: str) -> dict:
    exe = claude_cli_path()
    if not exe:
        raise RuntimeError(
            "Claude Code CLI ('claude') not found on PATH — install it or set "
            "ANTHROPIC_API_KEY to use the API instead"
        )
    # The prompt goes on stdin, never argv: the rubric alone is ~12k chars and
    # Windows caps a command line near 32k.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    cmd = [
        exe, "-p",
        "--max-turns", "1",          # one shot; never an agentic loop
        "--model", cfg.LLM_MODEL,
        "--append-system-prompt", system,
    ]
    try:
        r = subprocess.run(
            cmd, input=user, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300, env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Claude CLI timed out after 300s") from exc
    if r.returncode != 0:
        raise RuntimeError(
            f"Claude CLI failed (exit {r.returncode}): {(r.stderr or '').strip()[:300]}"
        )
    out = _strip_fence(r.stdout or "")
    if not out:
        raise RuntimeError("Claude CLI returned empty output")
    return json.loads(out)


def _complete_json_api(system: str, user: str, max_tokens: int) -> dict:
    resp = _api_client().messages.create(
        model=cfg.LLM_MODEL, max_tokens=max_tokens,
        system=system, messages=[{"role": "user", "content": user}],
    )
    return json.loads(_strip_fence(resp.content[0].text))


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _complete_json_ollama(system: str, user: str, max_tokens: int) -> dict:
    """Local model via Ollama. Free, offline, no rate limits, no API credits.

    `format: "json"` constrains decoding to valid JSON, which is what makes a
    small local model safe to put behind this pipeline — every caller here
    parses the result, so a prose preamble would break them.
    """
    import httpx

    payload = {
        "model": OLLAMA_MODEL,
        "format": "json",
        "stream": False,
        "think": False,  # Qwen3 emits <think> blocks otherwise
        "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": max_tokens},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        # Generous: a cold model load on a laptop GPU can take a minute, and
        # long rubric prompts are slow even warm.
        r = httpx.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=600)
        r.raise_for_status()
    except Exception as exc:
        raise RuntimeError(
            f"Local model call failed via Ollama at {OLLAMA_HOST} "
            f"(model={OLLAMA_MODEL}): {type(exc).__name__}: {str(exc)[:200]}. "
            "Is `ollama serve` running and the model pulled?"
        ) from exc
    content = (r.json().get("message") or {}).get("content", "")
    content = _strip_fence(_THINK.sub("", content).strip())
    if not content:
        raise RuntimeError(f"Local model {OLLAMA_MODEL} returned empty output")
    return json.loads(content)


def complete_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    p = provider()
    if p == "ollama":
        return _complete_json_ollama(system, user, max_tokens)
    if p == "cli":
        return _complete_json_cli(system, user)
    return _complete_json_api(system, user, max_tokens)
