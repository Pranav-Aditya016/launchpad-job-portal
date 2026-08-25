"""Plugin registry for job sources.

A source is added by creating ONE new file in `providers/` with an @register class.
No track ever edits this file or `api.py` to add a source — that is what makes the
five v2 tracks safe to run in parallel.
"""

from __future__ import annotations

import importlib
import pkgutil

from app.sources.base import Source

_REGISTRY: dict[str, Source] = {}
_LOADED = False


def register(cls):
    """Class decorator: instantiate once and record under `meta.key`.

    Returns the class unchanged so it stays independently importable and testable.
    """
    instance = cls()
    key = instance.meta.key
    if key in _REGISTRY:
        raise ValueError(
            f"duplicate source key {key!r} — {cls.__module__} collides with an "
            f"already-registered source"
        )
    _REGISTRY[key] = instance
    return cls


def load_providers() -> None:
    """Import every module under `providers/` so their @register calls run.

    Idempotent: repeated calls are a no-op, so app startup and tests can both
    call it freely.
    """
    global _LOADED
    if _LOADED:
        return
    from app.sources import providers

    for mod in pkgutil.iter_modules(providers.__path__):
        importlib.import_module(f"{providers.__name__}.{mod.name}")
    _LOADED = True


def all_sources() -> list[Source]:
    """Every registered source, sorted by key so the UI order never jitters."""
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def get(key: str) -> Source | None:
    return _REGISTRY.get(key)


def enabled_sources(overrides: dict[str, bool] | None = None) -> list[Source]:
    """Sources to actually run. A user's explicit toggle always beats the default."""
    overrides = overrides or {}
    return [
        s for s in all_sources()
        if overrides.get(s.meta.key, s.meta.enabled_by_default)
    ]


def clear() -> None:
    """Test-only: empty the registry and allow reloading."""
    global _LOADED
    _REGISTRY.clear()
    _LOADED = False
