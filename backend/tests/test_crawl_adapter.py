from app.sources import crawl_adapter as c


def test_jobs_from_markdown_extracts_links():
    md = "## Jobs\n- [ML Engineer](https://acme.com/jobs/1)\n- [Data Scientist](https://acme.com/jobs/2)\n"
    jobs = c.jobs_from_markdown(md, base_url="https://acme.com", company="acme")
    assert {j.title for j in jobs} == {"ML Engineer", "Data Scientist"}
    assert all(j.url.startswith("https://acme.com/jobs/") for j in jobs)
