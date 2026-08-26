"""Whole-suite guard: the real source registry must survive every test file.

Named `zz` so pytest's alphabetical collection runs it LAST. That is the point
— it asserts that no earlier test file left the process-wide registry empty.

This guard exists because the bug it catches has now happened twice. The
registry is a module-level singleton; any test file that clears it for
isolation must restore it, and restoring a snapshot taken *before*
`load_providers()` restores nothing. When that happens the suite does not go
red where the mistake was made — a different file fails much later with a
confusing "unknown portal 'naukri'", or worse, `/sources` quietly returns an
empty list in production while every test still passes.
"""

from app.sources import registry


def test_the_real_registry_is_still_populated():
    registry.load_providers()
    keys = {s.meta.key for s in registry.all_sources()}
    assert keys, (
        "the source registry is EMPTY at the end of the suite — an earlier "
        "test file cleared it and failed to restore it. Any fixture that calls "
        "registry.clear() must call registry.load_providers() BEFORE snapshotting."
    )
    for expected in ("naukri", "ats:greenhouse", "public:remotive", "custom:pages"):
        assert expected in keys, f"{expected!r} vanished from the registry"


def test_portal_sources_are_still_resolvable_by_key():
    """`/connections` and the session vault both look portals up by key."""
    registry.load_providers()
    assert registry.get("naukri") is not None
    assert registry.get("linkedin") is not None
