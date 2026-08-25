"""v2 dependency floors. Cheap, but these failing as ImportError deep inside a
scheduler tick is much harder to diagnose than failing here."""
import importlib


def test_v2_runtime_deps_importable():
    for mod in ("apscheduler", "sse_starlette", "playwright", "numpy"):
        assert importlib.import_module(mod) is not None


def test_anthropic_is_not_a_hard_dependency():
    """The product must run fully offline. `anthropic` may be installed on a dev
    box, but it must not be in the required dependency list."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    required = " ".join(data["project"]["dependencies"])
    assert "anthropic" not in required
    assert "anthropic" in " ".join(data["project"]["optional-dependencies"]["hosted"])
