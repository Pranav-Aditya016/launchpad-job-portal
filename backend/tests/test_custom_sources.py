"""User-supplied websites: "let me paste a link and scrape it".

Two halves:
  1. A small CRUD store so the user can add/remove their own sites.
  2. A link heuristic, because a naive "every link on the page is a job" turns
     nav bars, cookie notices and footers into fake job postings. The v1
     `crawl_adapter` did exactly that, which is why its own docstring called
     the results "best-effort" and "noisy".
"""

import pytest

from app import custom_sources as cs


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    from app import config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    return tmp_path


# --- store ------------------------------------------------------------------

def test_starts_empty():
    assert cs.load_all() == []


def test_add_then_load_round_trips():
    site = cs.add("https://careers.example.com/jobs", label="Example Careers",
                  regions=["in"])
    assert site.url == "https://careers.example.com/jobs"
    assert site.label == "Example Careers"
    loaded = cs.load_all()
    assert len(loaded) == 1 and loaded[0].id == site.id


def test_url_is_required_to_look_like_a_url():
    for bad in ("", "   ", "not a url", "ftp://x.com", "javascript:alert(1)"):
        with pytest.raises(ValueError):
            cs.add(bad)


def test_http_is_upgraded_to_https():
    assert cs.add("http://example.com/jobs").url.startswith("https://")


def test_a_missing_label_falls_back_to_the_host():
    assert cs.add("https://careers.acme.co.uk/openings").label == "careers.acme.co.uk"


def test_adding_the_same_url_twice_updates_rather_than_duplicating():
    a = cs.add("https://example.com/jobs", label="First")
    b = cs.add("https://example.com/jobs", label="Second")
    assert a.id == b.id
    all_ = cs.load_all()
    assert len(all_) == 1 and all_[0].label == "Second"


def test_remove_deletes_one_and_leaves_the_rest():
    a = cs.add("https://a.com/jobs")
    cs.add("https://b.com/jobs")
    assert cs.remove(a.id) is True
    assert [s.url for s in cs.load_all()] == ["https://b.com/jobs"]


def test_removing_something_that_is_not_there_returns_false():
    assert cs.remove("nope") is False


def test_a_site_can_be_disabled_without_being_deleted():
    a = cs.add("https://a.com/jobs")
    cs.set_enabled(a.id, False)
    assert cs.load_all()[0].enabled is False


def test_corrupt_store_reads_as_empty_rather_than_crashing(tmp_data):
    (tmp_data / "custom_sources.json").write_text("{not json", encoding="utf-8")
    assert cs.load_all() == []


# --- the link heuristic -----------------------------------------------------

MARKDOWN = """
[Home](https://acme.com/) [About us](https://acme.com/about)
[Privacy Policy](https://acme.com/privacy) [Log in](https://acme.com/login)
[Senior Backend Engineer](https://acme.com/careers/senior-backend-engineer)
[Data Analyst (Remote)](https://acme.com/jobs/1234)
[Cookie settings](https://acme.com/cookies)
[Apply here](https://boards.greenhouse.io/acme/jobs/998877)
[< Previous](https://acme.com/careers?page=1)
"""


def test_job_like_links_are_kept():
    jobs = cs.jobs_from_markdown(MARKDOWN, "https://acme.com/careers", "Acme", "custom:1")
    urls = {j.url for j in jobs}
    assert "https://acme.com/careers/senior-backend-engineer" in urls
    assert "https://acme.com/jobs/1234" in urls
    assert "https://boards.greenhouse.io/acme/jobs/998877" in urls


def test_navigation_and_boilerplate_links_are_dropped():
    jobs = cs.jobs_from_markdown(MARKDOWN, "https://acme.com/careers", "Acme", "custom:1")
    urls = {j.url for j in jobs}
    for junk in ("https://acme.com/", "https://acme.com/about",
                 "https://acme.com/privacy", "https://acme.com/login",
                 "https://acme.com/cookies"):
        assert junk not in urls, f"{junk} should have been filtered out"


def test_pagination_chrome_is_dropped():
    jobs = cs.jobs_from_markdown(MARKDOWN, "https://acme.com/careers", "Acme", "custom:1")
    assert not any(j.title.strip().startswith("<") for j in jobs)


def test_relative_links_are_resolved_against_the_page():
    jobs = cs.jobs_from_markdown(
        "[Platform Engineer](/careers/platform-engineer)",
        "https://acme.com/careers", "Acme", "custom:1")
    assert jobs[0].url == "https://acme.com/careers/platform-engineer"


def test_duplicate_links_are_collapsed():
    md = ("[Backend Engineer](https://acme.com/jobs/1)\n"
          "[Backend Engineer](https://acme.com/jobs/1)")
    assert len(cs.jobs_from_markdown(md, "https://acme.com", "Acme", "custom:1")) == 1


def test_jobs_carry_the_custom_source_key_so_provenance_survives():
    jobs = cs.jobs_from_markdown("[Engineer](https://acme.com/jobs/7)",
                                 "https://acme.com", "Acme", "custom:abc123")
    assert jobs[0].source == "custom:abc123"


def test_a_page_with_no_job_links_yields_nothing_rather_than_junk():
    md = "[Home](https://acme.com/) [Contact](https://acme.com/contact)"
    assert cs.jobs_from_markdown(md, "https://acme.com", "Acme", "custom:1") == []


# --- pagination -------------------------------------------------------------

def test_page_urls_walks_a_page_parameter():
    """A board URL like ?page=0 has more behind it. One page is not the site."""
    urls = cs.page_urls("https://jobfound.org/?page=0&loc=India", max_pages=3)
    assert urls == [
        "https://jobfound.org/?page=0&loc=India",
        "https://jobfound.org/?page=1&loc=India",
        "https://jobfound.org/?page=2&loc=India",
    ]


def test_page_urls_respects_a_non_zero_start():
    urls = cs.page_urls("https://x.com/jobs?page=2", max_pages=2)
    assert urls == ["https://x.com/jobs?page=2", "https://x.com/jobs?page=3"]


def test_page_urls_without_a_page_param_returns_just_the_one():
    urls = cs.page_urls("https://acme.com/careers", max_pages=5)
    assert urls == ["https://acme.com/careers"]


def test_page_urls_handles_alternative_param_names():
    assert cs.page_urls("https://x.com/j?p=1", max_pages=2) == [
        "https://x.com/j?p=1", "https://x.com/j?p=2",
    ]


def test_page_urls_never_returns_more_than_the_cap():
    assert len(cs.page_urls("https://x.com/j?page=0", max_pages=1)) == 1
