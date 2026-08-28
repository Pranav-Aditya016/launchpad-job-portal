"""Work out where a job actually is, from its location text.

This exists because region was previously copied from the SOURCE's first tag,
not the job. Every Greenhouse posting became "global" whether it was in
Bengaluru or Berlin, so the dashboard's region filter offered exactly two
useless options and no India at all — even though the user's whole search is
India, Germany and remote.

The rule: infer from the job's own `location` (falling back to title, then the
source hint). Unknown stays unknown rather than guessing — a wrong country is
worse than a blank, because the user filters on it.
"""

import pytest

from app import region


@pytest.mark.parametrize("text,expected", [
    ("Bengaluru, India", "in"),
    ("Bangalore", "in"),
    ("Hyderabad, Telangana", "in"),
    ("Chennai", "in"),
    ("Mumbai, Maharashtra, India", "in"),
    ("Pune", "in"),
    ("Noida", "in"),
    ("Gurugram", "in"),
    ("New Delhi", "in"),
    ("Nagercoil, Tamil Nadu", "in"),
    ("Remote - India", "in"),
])
def test_indian_locations(text, expected):
    assert region.infer(text) == expected


@pytest.mark.parametrize("text", [
    "Berlin, Germany", "München", "Munich", "Hamburg", "Frankfurt am Main",
    "Köln", "Cologne", "Stuttgart", "Deutschland", "Leipzig, DE",
])
def test_german_locations(text):
    assert region.infer(text) == "de"


@pytest.mark.parametrize("text", [
    "London, United Kingdom", "Manchester, UK", "Edinburgh, Scotland",
])
def test_uk_locations(text):
    assert region.infer(text) == "gb"


@pytest.mark.parametrize("text", [
    "San Francisco, CA", "New York, NY", "Seattle, Washington",
    "Austin, TX, United States", "Remote - US",
])
def test_us_locations(text):
    assert region.infer(text) == "us"


@pytest.mark.parametrize("text", [
    "Remote", "Remote - Worldwide", "Anywhere", "Fully remote",
])
def test_remote_is_global(text):
    assert region.infer(text) == "global"


def test_unknown_location_returns_empty_rather_than_guessing():
    """A wrong country is worse than a blank: the user filters on this."""
    assert region.infer("Atlantis") == ""
    assert region.infer("") == ""
    assert region.infer(None) == ""


def test_a_city_beats_a_bare_remote_mention():
    """'Remote, Berlin' is a German job, not an unplaceable one."""
    assert region.infer("Remote, Berlin") == "de"


def test_india_is_detected_even_with_extra_punctuation():
    assert region.infer("  bengaluru , karnataka , india  ") == "in"


def test_matching_is_word_boundary_not_substring():
    """'Ukraine' contains 'uk'; 'Indiana' contains 'india'. Neither should match."""
    assert region.infer("Kyiv, Ukraine") != "gb"
    assert region.infer("Indianapolis, Indiana") == "us"


def test_for_job_prefers_location_then_title_then_hint():
    from app.models import Job

    j = Job(id="1", source="s", company="c", title="Engineer",
            url="u", location="Berlin, Germany")
    assert region.for_job(j, source_hint="in") == "de"      # location wins

    j2 = Job(id="2", source="s", company="c", title="Engineer (Bengaluru)",
             url="u", location="")
    assert region.for_job(j2, source_hint="global") == "in"  # title used next

    j3 = Job(id="3", source="s", company="c", title="Engineer", url="u", location="")
    assert region.for_job(j3, source_hint="de") == "de"      # hint is the fallback

    j4 = Job(id="4", source="s", company="c", title="Engineer", url="u", location="")
    assert region.for_job(j4, source_hint="") == ""          # nothing to go on


def test_all_regions_exposes_the_filter_options():
    """The dashboard builds its region filter from this, so it must be stable
    and human-labelled rather than derived from whatever jobs happen to exist."""
    opts = dict(region.ALL_REGIONS)
    assert opts["in"] == "India"
    assert opts["de"] == "Germany"
    assert opts["global"] == "Remote / Global"
    for code in ("in", "de", "gb", "us", "eu", "global"):
        assert code in opts
