import pytest

from app.models import Job
from app.sources import registry
from app.sources.base import FetchContext, SourceKind, SourceMeta


@pytest.fixture(autouse=True)
def clean_registry():
    registry.clear()
    yield
    registry.clear()


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
