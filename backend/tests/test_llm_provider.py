"""Provider selection + the subscription (CLI) path.

The CLI path is what lets the app run on a Claude Pro/Max subscription with no
API key and no API credits, so its contract is worth pinning down.
"""
import json
import subprocess

import pytest

from app import llm


# POLICY CHANGE (v2): auto-selection resolves to the LOCAL model, always.
# These two tests previously pinned v1's "use whatever is available" order —
# API key first, then the Claude CLI, then Ollama. That meant any machine with
# `claude` on PATH silently sent every evaluation to Anthropic while the local
# GPU sat idle. v2 requires cloud to be opted into explicitly. The tests below
# now pin the new policy; see test_local_only_default.py for the full contract.

def test_a_stray_api_key_does_not_silently_select_the_cloud(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("LAUNCHPAD_LLM", raising=False)
    assert llm.provider() == "ollama"


def test_an_installed_claude_cli_does_not_silently_select_the_cloud(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LAUNCHPAD_LLM", raising=False)
    monkeypatch.setattr(llm, "claude_cli_path", lambda: "/usr/bin/claude")
    assert llm.provider() == "ollama"


def test_provider_explicit_override_wins(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("LAUNCHPAD_LLM", "cli")
    assert llm.provider() == "cli"


def test_cli_sends_prompt_on_stdin_and_strips_the_api_key(monkeypatch):
    """The prompt must not go on argv (Windows ~32k cap; the rubric alone is ~12k),
    and the API key must not leak into the subscription-auth subprocess."""
    monkeypatch.setattr(llm, "claude_cli_path", lambda: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-be-stripped")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["input"] = kw.get("input")
        seen["env"] = kw.get("env")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"score": 4.5}', stderr="")

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    out = llm._complete_json_cli("SYSTEM RUBRIC", "USER PROMPT")

    assert out == {"score": 4.5}
    assert seen["input"] == "USER PROMPT"           # stdin, not argv
    assert "USER PROMPT" not in " ".join(seen["cmd"])
    assert "ANTHROPIC_API_KEY" not in seen["env"]   # forced subscription auth
    assert "--max-turns" in seen["cmd"]             # never an agentic loop


def test_cli_surfaces_a_failure_clearly(monkeypatch):
    monkeypatch.setattr(llm, "claude_cli_path", lambda: "claude")
    monkeypatch.setattr(
        llm.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom"),
    )
    with pytest.raises(RuntimeError, match="Claude CLI failed"):
        llm._complete_json_cli("s", "u")


def test_cli_missing_binary_is_actionable(monkeypatch):
    monkeypatch.setattr(llm, "claude_cli_path", lambda: None)
    with pytest.raises(RuntimeError, match="not found on PATH"):
        llm._complete_json_cli("s", "u")


def test_json_fence_still_stripped_from_cli_output(monkeypatch):
    monkeypatch.setattr(llm, "claude_cli_path", lambda: "claude")
    monkeypatch.setattr(
        llm.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(
            cmd, 0, stdout='```json\n{"ok": true}\n```', stderr=""),
    )
    assert llm._complete_json_cli("s", "u") == {"ok": True}


def test_provider_falls_back_to_ollama_when_no_key_and_no_cli(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LAUNCHPAD_LLM", raising=False)
    monkeypatch.setattr(llm, "claude_cli_path", lambda: None)
    assert llm.provider() == "ollama"


def test_ollama_explicit_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("LAUNCHPAD_LLM", "ollama")
    assert llm.provider() == "ollama"


def test_ollama_forces_json_and_disables_thinking(monkeypatch):
    """format=json is what makes a small local model safe here: every caller
    parses the result, so a prose preamble would break the pipeline."""
    seen = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"message": {"content": '{"score": 3.5}'}}

    import httpx
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (seen.update(url=url, **kw), _Resp())[1])
    out = llm._complete_json_ollama("SYS", "USER", 1500)

    assert out == {"score": 3.5}
    body = seen["json"]
    assert body["format"] == "json"
    assert body["think"] is False
    assert body["messages"][0]["content"] == "SYS"
    assert body["messages"][1]["content"] == "USER"


def test_ollama_strips_think_blocks(monkeypatch):
    """Qwen3 can emit <think>…</think> even with think=False; it must not
    reach json.loads."""
    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"message": {"content": '<think>hmm let me reason</think>{"ok": true}'}}

    import httpx
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _Resp())
    assert llm._complete_json_ollama("s", "u", 100) == {"ok": True}


def test_ollama_unreachable_is_actionable(monkeypatch):
    import httpx
    def _boom(url, **kw): raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx, "post", _boom)
    with pytest.raises(RuntimeError, match="ollama serve"):
        llm._complete_json_ollama("s", "u", 100)
