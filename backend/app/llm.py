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


def provider() -> str:
    """Which backend a call will use right now: 'api' or 'cli'."""
    choice = (os.environ.get("LAUNCHPAD_LLM") or "auto").lower()
    if choice in ("api", "cli"):
        return choice
    return "api" if os.environ.get("ANTHROPIC_API_KEY") else "cli"


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


def complete_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    if provider() == "cli":
        return _complete_json_cli(system, user)
    return _complete_json_api(system, user, max_tokens)
