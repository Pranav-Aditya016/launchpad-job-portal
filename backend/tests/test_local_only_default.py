"""LaunchPad runs on a local model by default. Cloud is opt-in, never a fallback.

v1 chose its provider by "whatever is available": an API key won, then the
Claude Code CLI, and only then Ollama. On a machine that happens to have the
`claude` binary on PATH — which this one does — a normal `scripts/dev.ps1`
start silently sent every job evaluation to Anthropic instead of the GPU
sitting idle two feet away.

v2's rule: `auto` means local. Reaching a cloud provider requires the user to
say so explicitly with LAUNCHPAD_LLM.
"""

import pytest

from app import llm


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("LAUNCHPAD_LLM", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_default_is_local_even_when_the_claude_cli_is_installed(monkeypatch):
    monkeypatch.setattr(llm, "claude_cli_path", lambda: "/usr/bin/claude")
    assert llm.provider() == "ollama"


def test_default_is_local_even_when_an_api_key_is_present(monkeypatch):
    """A stray key in the environment must not silently start billing."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-whatever")
    assert llm.provider() == "ollama"


def test_default_is_local_when_nothing_else_is_available():
    assert llm.provider() == "ollama"


def test_explicit_opt_in_still_reaches_the_cloud(monkeypatch):
    """Opting in must keep working — this is not a ban, it is a default."""
    monkeypatch.setenv("LAUNCHPAD_LLM", "api")
    assert llm.provider() == "api"
    monkeypatch.setenv("LAUNCHPAD_LLM", "cli")
    assert llm.provider() == "cli"


def test_explicit_local_is_honoured(monkeypatch):
    monkeypatch.setenv("LAUNCHPAD_LLM", "ollama")
    assert llm.provider() == "ollama"


def test_an_unrecognised_value_falls_back_to_local_not_to_cloud(monkeypatch):
    """A typo in the env var must fail safe — toward the free, offline path."""
    monkeypatch.setenv("LAUNCHPAD_LLM", "gpt4")
    assert llm.provider() == "ollama"


def test_case_and_whitespace_are_tolerated(monkeypatch):
    monkeypatch.setenv("LAUNCHPAD_LLM", "  Ollama ")
    assert llm.provider() == "ollama"
    monkeypatch.setenv("LAUNCHPAD_LLM", " API ")
    assert llm.provider() == "api"
