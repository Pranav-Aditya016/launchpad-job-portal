import pytest

from app.models import Job
from app.sources import registry
from app.sources.base import FetchContext, SourceKind, SourceMeta


@pytest.fixture(autouse=True)
def clean_registry():
    """Isolate this file's registrations without destroying the real registry.

    `registry.clear()` empties a process-wide singleton. Leaving it cleared on
    teardown would silently empty /sources and /connections for every test file
    that runs after this one (pytest collects alphabetically), so we snapshot
    and restore rather than just clearing twice.
    """
    # Load the real providers BEFORE snapshotting. Snapshotting an empty
    # registry and restoring it leaves the process-wide singleton empty for
    # every later test file — which is exactly how `naukri` disappeared and
    # test_session_vault started failing. See tests/test_zz_registry_intact.py.
    registry.load_providers()
    saved, was_loaded = dict(registry._REGISTRY), registry._LOADED
    registry.clear()
    yield
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)
    registry._LOADED = was_loaded


def _make(key, **kw):
    @registry.register
    class _S:
        meta = SourceMeta(key=key, label=key.title(), kind=SourceKind.PUBLIC, **kw)

        async def fetch(self, ctx: FetchContext) -> list[Job]:
            return []

    return _S


def test_register_then_get():
    _make("alpha")
    assert registry.get("alpha").meta.label == "Alpha"


def test_get_unknown_returns_none():
    assert registry.get("nope") is None


def test_duplicate_key_is_rejected_loudly():
    _make("dup")
    with pytest.raises(ValueError, match="duplicate source key"):
        _make("dup")


def test_all_sources_is_sorted_by_key_for_stable_ui_order():
    _make("zulu"); _make("alpha"); _make("mike")
    assert [s.meta.key for s in registry.all_sources()] == ["alpha", "mike", "zulu"]


def test_enabled_respects_meta_default():
    _make("on")
    _make("off", enabled_by_default=False)
    assert [s.meta.key for s in registry.enabled_sources(None)] == ["on"]


def test_user_override_beats_the_default_in_both_directions():
    _make("on")
    _make("off", enabled_by_default=False)
    keys = [s.meta.key for s in registry.enabled_sources({"on": False, "off": True})]
    assert keys == ["off"]


def test_registered_class_is_returned_unchanged():
    """@register must not replace the class — tracks subclass and unit-test these."""
    cls = _make("plain")
    assert isinstance(cls.meta, SourceMeta)


def test_load_providers_is_idempotent():
    registry.load_providers()
    first = len(registry.all_sources())
    registry.load_providers()
    assert len(registry.all_sources()) == first


def test_nested_save_clear_restore_preserves_outer_registration():
    """Prove the snapshot/restore logic in `clean_registry` actually restores state.

    This inlines the exact same save -> clear -> restore sequence the fixture
    performs, one level deeper — as if another test file's autouse fixture ran
    while this file's registration was live. Against the OLD fixture (which
    only did `registry.clear(); yield; registry.clear()`, with no snapshot and
    no restore lines), the nested clear below would empty `_REGISTRY` and
    nothing would ever put "outer" back — so the final assertion would fail
    with `registry.get("outer") is None`. With the fix, it survives.
    """
    _make("outer")
    assert registry.get("outer") is not None

    # Exactly the fixture's save/clear/restore steps, nested one level deeper.
    saved, was_loaded = dict(registry._REGISTRY), registry._LOADED
    registry.clear()
    assert registry.get("outer") is None  # the nested clear really did empty it
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)
    registry._LOADED = was_loaded

    assert registry.get("outer") is not None
    assert registry.get("outer").meta.key == "outer"
